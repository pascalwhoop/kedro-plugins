"""SparkJDBCDataset to load and save a PySpark DataFrame via JDBC."""

from copy import deepcopy
from typing import Any

from kedro.io.core import AbstractDataset, DatasetError
from pyspark.sql import DataFrame

from kedro_datasets.spark.spark_dataset import _get_spark


class SparkJDBCDataset(AbstractDataset[DataFrame, DataFrame]):
    """``SparkJDBCDataset`` loads data from a database table accessible
    via JDBC URL url and connection properties and saves the content of
    a PySpark DataFrame to an external database table via JDBC.  It uses
    ``pyspark.sql.DataFrameReader`` and ``pyspark.sql.DataFrameWriter``
    internally, so it supports all allowed PySpark options on ``jdbc``.

    Example usage for the
    `YAML API <https://kedro.readthedocs.io/en/stable/data/\
    data_catalog_yaml_examples.html>`_:

    .. code-block:: yaml

        weather:
          type: spark.SparkJDBCDataset
          table: weather_table
          url: jdbc:postgresql://localhost/test
          credentials: db_credentials
          load_args:
            properties:
              driver: org.postgresql.Driver
          save_args:
            properties:
              driver: org.postgresql.Driver

    Example usage for the
    `Python API <https://kedro.readthedocs.io/en/stable/data/\
    advanced_data_catalog_usage.html>`_:

    .. code-block:: pycon

        >>> import pandas as pd
        >>> from kedro_datasets.spark import SparkJDBCDataset
        >>> from pyspark.sql import SparkSession
        >>>
        >>> spark = SparkSession.builder.getOrCreate()
        >>> data = spark.createDataFrame(
        ...     pd.DataFrame({"col1": [1, 2], "col2": [4, 5], "col3": [5, 6]})
        ... )
        >>> url = "jdbc:postgresql://localhost/test"
        >>> table = "table_a"
        >>> connection_properties = {"driver": "org.postgresql.Driver"}
        >>> dataset = SparkJDBCDataset(
        ...     url=url,
        ...     table=table,
        ...     credentials={"user": "scott", "password": "tiger"},
        ...     load_args={"properties": connection_properties},
        ...     save_args={"properties": connection_properties},
        ... )
        >>>
        >>> dataset.save(data)
        >>> reloaded = dataset.load()
        >>>
        >>> assert data.toPandas().equals(reloaded.toPandas())

    """

    DEFAULT_LOAD_ARGS: dict[str, Any] = {}
    DEFAULT_SAVE_ARGS: dict[str, Any] = {}

    def __init__(  # noqa: PLR0913
        self,
        *,
        url: str,
        table: str,
        credentials: dict[str, Any] = None,
        load_args: dict[str, Any] = None,
        save_args: dict[str, Any] = None,
        metadata: dict[str, Any] = None,
        query: str = None

    ) -> None:
        """Creates a new ``SparkJDBCDataset``.

        Args:
            url: A JDBC URL of the form ``jdbc:subprotocol:subname``.
            table: The name of the table to load or save data to.
            credentials: A dictionary of JDBC database connection arguments.
                Normally at least properties ``user`` and ``password`` with
                their corresponding values.  It updates ``properties``
                parameter in ``load_args`` and ``save_args`` in case it is
                provided.
            load_args: Provided to underlying PySpark ``jdbc`` function along
                with the JDBC URL and the name of the table. To find all
                supported arguments, see here:
                https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrameWriter.jdbc.html
            save_args: Provided to underlying PySpark ``jdbc`` function along
                with the JDBC URL and the name of the table. To find all
                supported arguments, see here:
                https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrameWriter.jdbc.html
            metadata: Any arbitrary metadata.
                This is ignored by Kedro, but may be consumed by users or external plugins.

        Raises:
            DatasetError: When either ``url`` or ``table`` is empty or
                when a property is provided with a None value.
        """

        if not url:
            raise DatasetError(
                "'url' argument cannot be empty. Please "
                "provide a JDBC URL of the form "
                "'jdbc:subprotocol:subname'."
            )

        if not table and not query:
            raise DatasetError(
                "'table'  and 'query' argument cannot be both empty. Please "
                "provide the name of the table to load or save "
                "data to."
            )

        if  table and  query:
            raise DatasetError(
                "Only one of 'table'  and 'query' argument should be used. Please "
                "provide the name of the table or a query."
            )

        self._url = url
        self._table = table
        self._query = query

        self.metadata = metadata

        # Handle default load and save arguments
        self._load_args = deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)
        self._save_args = deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

        # Update properties in load_args and save_args with credentials.
        if credentials is not None:
            # Check credentials for bad inputs.
            for cred_key, cred_value in credentials.items():
                if cred_value is None:
                    raise DatasetError(
                        f"Credential property '{cred_key}' cannot be None. "
                        f"Please provide a value."
                    )

            load_properties = self._load_args.get("properties", {})
            save_properties = self._save_args.get("properties", {})
            self._load_args["properties"] = {**load_properties, **credentials}
            self._save_args["properties"] = {**save_properties, **credentials}

    def _describe(self) -> dict[str, Any]:
        load_args = self._load_args
        save_args = self._save_args

        # Remove user and password values from load and save properties.
        if "properties" in load_args:
            load_properties = load_args["properties"].copy()
            load_properties.pop("user", None)
            load_properties.pop("password", None)
            load_args = {**load_args, "properties": load_properties}
        if "properties" in save_args:
            save_properties = save_args["properties"].copy()
            save_properties.pop("user", None)
            save_properties.pop("password", None)
            save_args = {**save_args, "properties": save_properties}

        return {
            "url": self._url,
            "table": self._table,
            "load_args": load_args,
            "save_args": save_args,
        }

    def _load(self) -> DataFrame:
        if self._table:
            return _get_spark().read.jdbc(self._url, self._table, **self._load_args)
        if self._query:
            return _get_spark().read.format("jdbc").option("url", self._url).option("query", self._query).load()


    def _save(self, data: DataFrame) -> None:
        return data.write.jdbc(self._url, self._table, **self._save_args)
