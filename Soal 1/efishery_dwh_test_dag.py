import imp
import pytz
import time
from datetime import datetime
from airflow.models.dag import DAG
from airflow.decorators import task
from airflow.utils.task_group import TaskGroup
from airflow.operators.mssql_operator import MsSqlHook
from airflow.hooks.base_hook import BaseHook
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
import pandas as pd
from sqlalchemy import create_engine

#extract tasks
@task()
def _get_src_tables():
    hook = MsSqlHook(mssql_conn_id="sqlserver")
    conn = BaseHook.get_connection('postgres')
    engine = create_engine(f'postgresql://{conn.login}:{conn.password}@{conn.host}:{conn.port}/{conn.schema}')
    sql = """ select * from customers """
    sql = """ select 
	    1 AS order_date_id,
	    1 AS invoice_date_id,
	    1 AS payment_date_id,
	    c.customer_id,
	    c.order_number,
	    a.invoice_number,
	    b.payment_number,
	    cast(count(c.order_number) as int) as total_order_quantity,
	    sum(d.usd_amount) as total_order_usd_amount,
	    (a.date - c.date) as order_to_invoice_lag_days,
	    (b.date - a.date) as invoice_to_payment_lag_days
        from invoices a
        full join payments b on a.invoice_number = b.invoice_number
        full join orders c on a.order_number = c.order_number
        full join order_lines d on c.order_number = d.order_number
        group by c.customer_id, c.order_number, a.invoice_number, b.payment_number """
    sql = """select 1 as id,
	    to_date(to_char(current_date, 'yyyy-mm-dd'), 'yyyy-mm-dd') as date,
	    cast(to_char(current_date, 'mm') as int) as month,
	    cast(extract(quarter from current_date) as int) as quarter_of_year,
	    cast(to_char(current_date, 'yyyy') as int) as year,
	    case when extract(isodow from current_date) = 6 then true
	   		 when extract(isodow from current_date) = 7 then true
			 else false end as is_weekend"""
    df = hook.get_pandas_df(sql)
    print(df)
    tbl_dict = df.to_dict('dict')
    return tbl_dict

# load task
@task()
def _load_src_data(tbl_dict: dict):
    conn = BaseHook.get_connection('postgres')
    engine = create_engine(f'postgresql://{conn.login}:{conn.password}@{conn.host}:{conn.port}/{conn.schema}')
    all_tbl_name = []
    start_time = time.time()
    #access the table_name element in dictionaries
    for k, v in tbl_dict['table_name'].items():
        #print(v)
        all_tbl_name.append(v)
        rows_imported = 0
        sql = f'select * FROM {v}'
        hook = MsSqlHook(mssql_conn_id="sqlserver")
        df = hook.get_pandas_df(sql)
        print(f'importing rows {rows_imported} to {rows_imported + len(df)}... for table {v} ')
        df.to_sql(f'src_{v}', engine, if_exists='replace', index=False)
        rows_imported += len(df)
        print(f'Done. {str(round(time.time() - start_time, 2))} total seconds elapsed')
    print("Data imported successful")
    return all_tbl_name


with DAG("efisher_dwh_test_dag", start_date=datetime(2022, 9, 3, tzinfo=pytz.timezone('Asia/Jakarta')), schedule_interval="@daily", catchup=False) as dag:
    get_src_tables = PythonOperator(
        task_id = "get_src_tables",
        python_callable = _get_src_tables
    )

    load_src_data = PythonOperator(
        task_id = "load_src_data"
        python_callable = _load_src_data
    )

    get_src_tables >> load_src_data