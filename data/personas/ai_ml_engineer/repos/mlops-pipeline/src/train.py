import mlflow

with mlflow.start_run(run_name="mlops-pipeline"):
    model = train(X_train, y_train)
    mlflow.log_metric("val_score", evaluate(model, X_val, y_val))
    mlflow.sklearn.log_model(model, "model")
