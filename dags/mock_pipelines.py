"""
Mock DAGs for testing DataSight AI.

These DAGs simulate:
1. A healthy ELT pipeline that always succeeds
2. A broken dbt pipeline that fails with a column mismatch error
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


# ── Shared defaults ──────────────────────────────────────────────────
default_args = {
    "owner": "data_engineering",
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}


# ── DAG 1: Successful ELT Pipeline ──────────────────────────────────
def extract_sales_data(**kwargs):
    """Simulates extracting data from a source database."""
    import time
    time.sleep(2)
    print("Extracted 10,000 rows from sales_db.transactions")
    return {"rows_extracted": 10000}


def run_dbt_transform(**kwargs):
    """Simulates a successful dbt transformation."""
    import time
    time.sleep(1)
    print("dbt run completed: 3 models passed, 0 failed")


def load_to_warehouse(**kwargs):
    """Simulates loading data into the data warehouse."""
    import time
    time.sleep(1)
    print("Loaded 10,000 rows into warehouse.fact_sales")


with DAG(
    dag_id="successful_elt_pipeline",
    description="A mock pipeline that always succeeds",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=timedelta(minutes=10),
    catchup=False,
    tags=["elt", "mock"],
) as dag1:
    t1 = PythonOperator(task_id="extract_sales_data", python_callable=extract_sales_data)
    t2 = PythonOperator(task_id="run_dbt_transform", python_callable=run_dbt_transform)
    t3 = PythonOperator(task_id="load_to_warehouse", python_callable=load_to_warehouse)
    t1 >> t2 >> t3


# ── DAG 2: Failing dbt Pipeline ─────────────────────────────────────
def extract_users(**kwargs):
    """Simulates extracting user data."""
    print("Extracted 5,000 rows from app_db.users")
    return {"rows": 5000}


def broken_transform(**kwargs):
    """Simulates a dbt model that fails due to a column mismatch."""
    print("Running dbt model: stg_users")
    print("Compiling SQL:")
    print("""
    SELECT
        user_id,
        first_name,
        last_name,
        user_email as email,    -- ERROR: column 'user_email' does not exist
        created_at
    FROM raw_users
    """)
    print("ERROR: column \"user_email\" does not exist")
    print('HINT:  Perhaps you meant to reference the column "raw_users.email_address".')
    print("LINE 4:     user_email as email,")
    raise Exception("dbt run failed due to missing column.")


with DAG(
    dag_id="failing_dbt_pipeline",
    description="A mock pipeline that simulates a dbt compilation error",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=timedelta(minutes=5),
    catchup=False,
    tags=["dbt_failure", "mock"],
) as dag2:
    u1 = PythonOperator(task_id="extract_users", python_callable=extract_users)
    u2 = PythonOperator(task_id="run_dbt_models", python_callable=broken_transform)
    u1 >> u2
