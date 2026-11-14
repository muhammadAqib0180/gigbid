from airflow import DAG
from airflow.operators.python import PythonOperator

with DAG("mlops-pipeline_daily", schedule="0 5 * * *", catchup=False, default_args={"retries": 2}) as dag:
    extract = PythonOperator(task_id="extract", python_callable=extract_sources)
    load = PythonOperator(task_id="load", python_callable=load_warehouse)
    extract >> load
