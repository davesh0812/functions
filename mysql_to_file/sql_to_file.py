
import pandas as pd
import pyhive
from sqlalchemy.engine import create_engine
from mlrun.execution import MLClientCtx


def sql_to_file(
    context: MLClientCtx,
    sql_query: str,
    database_url: str,
    file_ext: str = "parquet",
) -> None:
    """SQL Ingest - Ingest data using SQL query

    :param context:           the function context
    :param sql_query:         the sql query used to retrieve the data
    :param database_url:      database connection URL
    :param file_ext:          ("parquet") format for result file

"""

    engine = create_engine(database_url)
    df = pd.read_sql(sql_query, engine)

    context.log_dataset('query result',
                        df=df,
                        format=file_ext,
                        artifact_path=context.artifact_subpath('data'))
