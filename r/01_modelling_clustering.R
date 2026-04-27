#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(ggplot2)
  library(tidyr)
  library(stringr)
  library(tidymodels)
  library(cluster)
  library(factoextra)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: Rscript r/01_modelling_clustering.R artifacts/features.parquet")
}

features_path <- args[[1]]
out_dir <- file.path("artifacts", "r")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

df <- read_parquet(features_path) %>% as_tibble()

# Basic label/score sanity
df <- df %>%
  mutate(
    y_compromise = as.integer(y_compromise),
    anomaly_score = as.numeric(anomaly_score)
  ) %>%
  filter(!is.na(anomaly_score))

# --------- Predictive modelling (which features predict compromise?) ----------
# We intentionally use a simple, explainable baseline + a stronger model

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

# Feature importance (RF)
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
  labs(title = "Top RF feature importances (impurity)", x = NULL, y = "importance")
ggsave(file.path(out_dir, "rf_feature_importance_top25.png"), p_imp, width = 10, height = 6, dpi = 160)

# --------- Clustering (unknown behavior groups) ----------
# Cluster device-hour behavior using numeric telemetry and simple flags.

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

# Choose k with a simple heuristic range; in a report you can show a silhouette plot.
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

