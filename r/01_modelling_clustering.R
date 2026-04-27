#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(dplyr)
  library(ggplot2)
  library(tidyr)
  library(stringr)
  library(tidymodels)
  library(cluster)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1) {
  features_path <- args[[1]]
} else {
  features_path <- "artifacts/features.csv"
}
out_dir <- file.path("artifacts", "r")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

read_feature_table <- function(path) {
  is_parq <- grepl("\\.parquet$", path, ignore.case = TRUE)
  is_csv <- grepl("\\.csv$", path, ignore.case = TRUE)
  if (is_parq && requireNamespace("arrow", quietly = TRUE) && file.exists(path)) {
    return(arrow::read_parquet(path) %>% tibble::as_tibble())
  }
  if (is_parq) {
    path <- sub("\\.parquet$", ".csv", path, ignore.case = TRUE)
  }
  if (!file.exists(path)) {
    stop("Cannot find ", path, " run python 01 first to build features csv")
  }
  if (requireNamespace("readr", quietly = TRUE)) {
    return(readr::read_csv(path, show_col_types = FALSE, progress = FALSE))
  }
  tibble::as_tibble(utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE))
}

df <- read_feature_table(features_path)

# Basic label and score checks
df <- df %>%
  mutate(
    y_compromise = as.integer(y_compromise),
    anomaly_score = as.numeric(anomaly_score)
  ) %>%
  filter(!is.na(anomaly_score))

# Predictive modelling. Simple logit and a random forest

set.seed(42)
split <- initial_split(df, prop = 0.8, strata = y_compromise)
train <- training(split)
test <- testing(split)

rec <- recipe(
  y_compromise ~ device_type + building + floor + room + protocol + port +
    bytes_in + bytes_out + packets + cpu_load_pct + memory_usage_pct + battery_level_pct +
    temperature_c + out_in_ratio + bytes_out_per_packet +
    hour_sin + hour_cos + dow_sin + dow_cos +
    signed_firmware + firmware_integrity + identity_mismatch + protocol_misuse_flag,
  data = train
) %>%
  step_mutate(
    across(c(floor, port), ~ as.numeric(.x)),
    across(c(signed_firmware, identity_mismatch, protocol_misuse_flag), ~ as.factor(.x))
  ) %>%
  step_unknown(all_nominal_predictors()) %>%
  step_other(all_nominal_predictors(), threshold = 0.01) %>%
  step_nzv(all_predictors()) %>%
  step_impute_median(all_numeric_predictors()) %>%
  step_impute_mode(all_nominal_predictors()) %>%
  step_dummy(all_nominal_predictors()) %>%
  step_normalize(all_numeric_predictors())

glm_spec <- logistic_reg(penalty = 0.0, mixture = 0.0) %>% set_engine("glm")
rf_spec <- rand_forest(trees = 400, min_n = 10) %>% set_engine("ranger", importance = "impurity") %>% set_mode("classification")

glm_wf <- workflow() %>% add_recipe(rec) %>% add_model(glm_spec)
rf_wf <- workflow() %>% add_recipe(rec) %>% add_model(rf_spec)

glm_fit <- fit(glm_wf, train)
rf_fit <- fit(rf_wf, train)

glm_pred <- predict(glm_fit, test, type = "prob") %>% bind_cols(test %>% select(y_compromise))
rf_pred <- predict(rf_fit, test, type = "prob") %>% bind_cols(test %>% select(y_compromise))

metrics <- metric_set(roc_auc, pr_auc, accuracy, sensitivity, specificity)
glm_m <- metrics(glm_pred, truth = factor(y_compromise), .pred_1)
rf_m <- metrics(rf_pred, truth = factor(y_compromise), .pred_1)

write.csv(glm_m, file.path(out_dir, "glm_metrics.csv"), row.names = FALSE)
write.csv(rf_m, file.path(out_dir, "rf_metrics.csv"), row.names = FALSE)

# Random forest importances
rf_engine <- extract_fit_engine(rf_fit)
imp <- tibble::tibble(
  feature = names(rf_engine$variable.importance),
  importance = as.numeric(rf_engine$variable.importance)
) %>%
  arrange(desc(importance)) %>%
  slice_head(n = 25)

write.csv(imp, file.path(out_dir, "rf_feature_importance_top25.csv"), row.names = FALSE)

p_imp <- ggplot(imp, aes(x = reorder(feature, importance), y = importance)) +
  geom_col(fill = "#2E86AB") +
  coord_flip() +
  labs(title = "Top random forest feature strength by impurity", x = NULL, y = "importance")
ggsave(file.path(out_dir, "rf_feature_importance_top25.png"), p_imp, width = 10, height = 6, dpi = 160)

# Clustering. Numeric fields from each row

cluster_df <- df %>%
  select(
    device_id, device_type, building, floor, room,
    bytes_in, bytes_out, packets, cpu_load_pct, memory_usage_pct, battery_level_pct, temperature_c,
    out_in_ratio, bytes_out_per_packet,
    anomaly_score, y_compromise
  ) %>%
  mutate(across(where(is.character), ~ replace_na(.x, "(missing)"))) %>%
  mutate(across(where(is.numeric), ~ replace_na(.x, median(.x, na.rm = TRUE))))

num_mat <- cluster_df %>%
  select(where(is.numeric), -y_compromise) %>%
  scale() %>%
  as.matrix()

# k from a few candidates using mean silhouette. You can plot silhouette in the report
ks <- 2:6
sil <- sapply(ks, function(k) {
  km <- kmeans(num_mat, centers = k, nstart = 10)
  ss <- silhouette(km$cluster, dist(num_mat))
  mean(ss[, 3])
})

best_k <- ks[which.max(sil)]
km <- kmeans(num_mat, centers = best_k, nstart = 25)
cluster_df$cluster <- factor(km$cluster)

write.csv(
  data.frame(k = ks, mean_silhouette = sil),
  file.path(out_dir, "cluster_silhouette_summary.csv"),
  row.names = FALSE
)

cluster_summary <- cluster_df %>%
  group_by(cluster) %>%
  summarise(
    n = n(),
    compromise_rate = mean(y_compromise),
    mean_anomaly = mean(anomaly_score),
    mean_bytes_out = mean(bytes_out),
    mean_out_in_ratio = mean(out_in_ratio),
    .groups = "drop"
  ) %>%
  arrange(desc(compromise_rate))

write.csv(cluster_summary, file.path(out_dir, "cluster_summary.csv"), row.names = FALSE)

p_cluster <- ggplot(cluster_summary, aes(x = cluster, y = compromise_rate, fill = cluster)) +
  geom_col(show.legend = FALSE) +
  labs(title = "Compromise rate by behavior cluster", x = "cluster", y = "compromise rate")
ggsave(file.path(out_dir, "cluster_compromise_rate.png"), p_cluster, width = 8, height = 4.5, dpi = 160)

message("Wrote R outputs to ", out_dir, " (best_k=", best_k, ")")

