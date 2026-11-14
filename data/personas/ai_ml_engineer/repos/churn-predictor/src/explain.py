import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_customer)
top_reasons = rank_features(shap_values)
