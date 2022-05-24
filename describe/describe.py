# Generated by nuclio.export.NuclioExporter

import warnings
from typing import Union

import matplotlib.pyplot as plt
import mlrun
import numpy as np
import seaborn as sns

warnings.simplefilter(action="ignore", category=FutureWarning)

import mlrun.feature_store as fstore
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go
from mlrun.artifacts import (DatasetArtifact, PlotArtifact, PlotlyArtifact,
                             TableArtifact, update_dataset_meta)
from mlrun.datastore import DataItem
from mlrun.execution import MLClientCtx
from mlrun.feature_store import FeatureSet, FeatureVector
from plotly.subplots import make_subplots

pd.set_option("display.float_format", lambda x: "%.2f" % x)
MAX_SIZE_OF_DF = 500000


def analyze(
    context: MLClientCtx,
    name: str = "dataset",
    table: Union[FeatureSet, DataItem] = None,
    label_column: str = None,
    plots_dest: str = "plots",
    random_state: int = 1,
    problem_type: str = "classification",
    dask_key: str = "dask_key",
    dask_function: str = None,
    dask_client=None,
) -> None:
    """
    The function will output the following artifacts per
    column within the data frame (based on data types)
    If the data has more than 500,000 sample we
    sample randomly 500,000 samples:

    describe csv
    histograms
    scatter-2d
    violin chart
    correlation-matrix chart
    correlation-matrix csv
    imbalance pie chart
    imbalance-weights-vec csv

    :param context:                 The function context
    :param name:                    Key of dataset to database ("dataset" for default)
    :param table:                   MLRun input pointing to pandas dataframe (csv/parquet file path) or FeatureSet
                                    as param
    :param label_column:            Ground truth column label
    :param plots_dest:              Destination folder of summary plots (relative to artifact_path)
                                    ("plots" for default)
    :param random_state:            When the table has more than 500,000 samples, we sample randomly 500,000 samples
    :param problem_type             The type of the ML problem the data facing - regression, classification or None
                                    (classification for default)
    :param dask_key:                Key of dataframe in dask client "datasets" attribute
    :param dask_function:           Dask function url (db://..)
    :param dask_client:             Dask client object
    """
    data_item, featureset, creat, update = False, False, False, False
    get_from_table = True
    if dask_function or dask_client:
        data_item, creat = True, True
        if dask_function:
            client = mlrun.import_function(dask_function).client
        elif dask_client:
            client = dask_client
        else:
            raise ValueError("dask client was not provided")

        if dask_key in client.datasets:
            df = client.get_dataset(dask_key)
            data_item, creat, get_from_table = True, True, False
        elif table:
            get_from_table = True
        else:
            context.logger.info(
                f"only these datasets are available {client.datasets} in client {client}"
            )
            raise Exception("dataset not found on dask cluster")

    if get_from_table:
        if type(table) == DataItem:
            if table.meta is None:
                data_item, creat, update = True, True, False
            elif table.meta.kind == "dataset":
                data_item, creat, update = True, False, True
            elif table.meta.kind == "FeatureVector":
                data_item, creat, update = True, False, False
            elif table.meta.kind == "FeatureSet":
                featureset, creat, update = True, False, False

        if data_item:
            df = table.as_df()
        elif featureset:
            project_name, set_name = (
                table._path.split("/")[2],
                table._path.split("/")[4],
            )
            feature_set = fstore.get_feature_set(
                f"store://feature-sets/{project_name}/{set_name}"
            )
            df = feature_set.to_dataframe()
        else:
            context.logger.error(f"Wrong table type.")
            return

    if df.size > MAX_SIZE_OF_DF:
        df = df.sample(n=MAX_SIZE_OF_DF, random_state=random_state)
    extra_data = {}

    if label_column not in df.columns:
        label_column = None

    extra_data["describe csv"] = context.log_artifact(
        TableArtifact("describe-csv", df=df.describe()),
        local_path=f"{plots_dest}/describe.csv",
    )

    try:
        _create_histogram_mat_artifact(
            context, df, extra_data, label_column, plots_dest
        )
    except Exception as e:
        context.logger.warn(f"Failed to create histogram matrix artifact due to: {e}")
    try:
        _create_features_histogram_artifacts(
            context, df, extra_data, label_column, plots_dest, problem_type
        )
    except Exception as e:
        context.logger.warn(f"Failed to create pairplot histograms due to: {e}")
    try:
        _create_features_2d_scatter_artifacts(
            context, df, extra_data, label_column, plots_dest, problem_type
        )
    except Exception as e:
        context.logger.warn(f"Failed to create pairplot 2d_scatter due to: {e}")
    try:
        _create_violin_artifact(context, df, extra_data, plots_dest)
    except Exception as e:
        context.logger.warn(f"Failed to create violin distribution plots due to: {e}")
    try:
        _create_imbalance_artifact(
            context, df, extra_data, label_column, plots_dest, problem_type
        )
    except Exception as e:
        context.logger.warn(f"Failed to create class imbalance plot due to: {e}")
    try:
        _create_corr_artifact(context, df, extra_data, label_column, plots_dest)
    except Exception as e:
        context.logger.warn(f"Failed to create features correlation plot due to: {e}")

    if not data_item:
        return

    artifact = table.artifact_url
    if creat:  # dataset not stored
        artifact = DatasetArtifact(
            key="dataset", stats=True, df=df, extra_data=extra_data
        )
        artifact = context.log_artifact(artifact, db_key=name)
        context.logger.info(f"The data set is logged to the project under {name} name")

    if update:
        update_dataset_meta(artifact, extra_data=extra_data)
        context.logger.info(f"The data set named {name} is updated")

    # TODO : 3-D plot on on selected features.
    # TODO : Reintegration plot on on selected features.
    # TODO : PCA plot (with options)


def _create_histogram_mat_artifact(
    context: MLClientCtx,
    df: pd.DataFrame,
    extra_data: dict,
    label_column: str,
    plots_dest: str,
):
    """
    Create and log a histogram matrix artifact
    """

    # fig = ff.create_scatterplotmatrix(df, diag="box", width=2500, height=2500)
    # if label_column is not None:
    #     df_new = df.copy()
    #     df_new[label_column] = df_new[label_column].apply(str)
    #     fig = ff.create_scatterplotmatrix(
    #         df_new, diag="box", index=label_column, width=2500, height=2500
    #     )
    # fig.update_layout(title_text="<i><b>Histograms matrix</b></i>")
    # extra_data["histogram-matrix"] = context.log_artifact(
    #     PlotlyArtifact(key="histograms-matrix", figure=fig),
    #     local_path=f"{plots_dest}/hist_mat.html",
    # )
    context.log_artifact(f"{plots_dest}/hist.html", body=b'<b> Deprecated, see the artifacts scatter-2d and '
                                                         b'histograms instead<b>', viewer='web-app')

#     snsplt = sns.pairplot(df, hue=label_column)  # , diag_kws={"bw": 1.5})
#     extra_data["histograms-matrix"] = context.log_artifact(
#         PlotArtifact("histograms-matrix", body=plt.gcf()),
#         local_path=f"{plots_dest}/hist.html",
#         db_key=False,
#     )


def _create_features_histogram_artifacts(
    context: MLClientCtx,
    df: pd.DataFrame,
    extra_data: dict,
    label_column: str,
    plots_dest: str,
    problem_type: str,
):
    """
    Create and log a histogram artifact for each feature
    """

    figs = dict()
    first_feature_name = ""
    if label_column is not None and problem_type == "classification":
        all_labels = df[label_column].unique()
    visible = True
    for (columnName, _) in df.iteritems():
        if columnName == label_column:
            continue

        if label_column is not None and problem_type == "classification":
            for label in all_labels:
                sub_fig = go.Histogram(
                    histfunc="count",
                    x=df.loc[df[label_column] == label][columnName],
                    name=str(label),
                    visible=visible,
                )
                figs[f"{columnName}@?@{label}"] = sub_fig
        else:
            sub_fig = go.Histogram(histfunc="count", x=df[columnName], visible=visible)
            figs[f"{columnName}@?@{1}"] = sub_fig
        if visible:
            first_feature_name = columnName
        visible = False

    fig = go.Figure()
    for k in figs.keys():
        fig.add_trace(figs[k])

    fig.update_layout(
        updatemenus=[
            {
                "buttons": [
                    {
                        "label": column_name,
                        "method": "update",
                        "args": [
                            {
                                "visible": [
                                    key.split("@?@")[0] == column_name
                                    for key in figs.keys()
                                ]
                            },
                            {"title": f"<i><b>Histogram of {column_name}</b></i>"},
                        ],
                    }
                    for column_name in df.columns
                    if column_name != label_column
                ],
                "direction": "down",
                "pad": {"r": 10, "t": 10},
                "showactive": True,
                "x": 0.25,
                "xanchor": "left",
                "y": 1.1,
                "yanchor": "top",
            }
        ],
        annotations=[
            dict(
                text="Select Feature Name ",
                showarrow=False,
                x=0,
                y=1.05,
                yref="paper",
                xref="paper",
                align="left",
                xanchor="left",
                yanchor="top",
                font={
                    "color": "blue",
                },
            )
        ],
    )

    fig.update_layout(
        width=600,
        height=400,
        autosize=False,
        margin=dict(t=100, b=0, l=0, r=0),
        template="plotly_white",
    )

    fig.update_layout(title_text=f"<i><b>Histograms of {first_feature_name}</b></i>")
    extra_data[f"histograms"] = context.log_artifact(
        PlotlyArtifact(key=f"histograms", figure=fig),
        local_path=f"{plots_dest}/histograms.html",
    )


def _create_features_2d_scatter_artifacts(
    context: MLClientCtx,
    df: pd.DataFrame,
    extra_data: dict,
    label_column: str,
    plots_dest: str,
    problem_type: str,
):
    """
    Create and log a scatter-2d artifact for each couple of features
    """
    features = [
        columnName for (columnName, _) in df.iteritems() if columnName != label_column
    ]
    max_feature_len = float(max(len(elem) for elem in features))
    if label_column is not None:
        labels = sorted(df[label_column].unique())
    else:
        labels = [None]
    fig = go.Figure()
    if label_column is not None and problem_type == "classification":
        for l in labels:
            fig.add_trace(
                go.Scatter(
                    x=df.loc[df[label_column] == l][features[0]],
                    y=df.loc[df[label_column] == l][features[0]],
                    mode="markers",
                    visible=True,
                    showlegend=True,
                    name=str(l),
                )
            )
    elif label_column is None:
        fig.add_trace(
            go.Scatter(
                x=df[features[0]],
                y=df[features[0]],
                mode="markers",
                visible=True,
            )
        )
    elif problem_type == "regression":
        fig.add_trace(
            go.Scatter(
                x=df[features[0]],
                y=df[features[0]],
                mode="markers",
                marker=dict(
                    color=df[label_column], colorscale="Viridis", showscale=True
                ),
                visible=True,
            )
        )

    x_buttons = []
    y_buttons = []

    for ncol in features:
        if problem_type == "classification" and label_column is not None:
            x_buttons.append(
                dict(
                    method="update",
                    label=ncol,
                    args=[
                        {"x": [df.loc[df[label_column] == l][ncol] for l in labels]},
                        np.arange(len(labels)).tolist(),
                    ],
                )
            )

            y_buttons.append(
                dict(
                    method="update",
                    label=ncol,
                    args=[
                        {"y": [df.loc[df[label_column] == l][ncol] for l in labels]},
                        np.arange(len(labels)).tolist(),
                    ],
                )
            )
        else:
            x_buttons.append(
                dict(method="update", label=ncol, args=[{"x": [df[ncol]]}])
            )

            y_buttons.append(
                dict(method="update", label=ncol, args=[{"y": [df[ncol]]}])
            )

    # Pass buttons to the updatemenus argument
    fig.update_layout(
        updatemenus=[
            dict(buttons=x_buttons, direction="up", x=0.5, y=-0.1),
            dict(buttons=y_buttons, direction="down", x=-max_feature_len / 100, y=0.5),
        ]
    )

    fig.update_layout(
        width=600,
        height=400,
        autosize=False,
        margin=dict(t=100, b=0, l=0, r=0),
        template="plotly_white",
    )

    fig.update_layout(title_text=f"<i><b>Scatter-2d</b></i>")
    extra_data[f"scatter-2d"] = context.log_artifact(
        PlotlyArtifact(key=f"scatter-2d", figure=fig),
        local_path=f"{plots_dest}/scatter-2d.html",
    )


def _create_violin_artifact(
    context: MLClientCtx, df: pd.DataFrame, extra_data: dict, plots_dest: str
):
    """
    Create and log a violin artifact
    """
    cols = 5
    rows = (df.shape[1] // cols) + 1
    fig = make_subplots(rows=rows, cols=cols)

    plot_num = 0

    for (columnName, columnData) in df.iteritems():
        violin = go.Violin(
            x=[columnName] * columnData.shape[0],
            y=columnData,
            name=columnName,
        )

        fig.add_trace(
            violin,
            row=(plot_num // cols) + 1,
            col=(plot_num % cols) + 1,
        )

        plot_num += 1

    fig["layout"].update(
        height=(rows + 1) * 200,
        width=(cols + 1) * 200,
        title="<i><b>Violin Plots</b></i>",
    )

    fig.update_layout(showlegend=False)
    extra_data["violin"] = context.log_artifact(
        PlotlyArtifact(key="violin", figure=fig),
        local_path=f"{plots_dest}/violin.html",
    )


def _create_imbalance_artifact(
    context: MLClientCtx,
    df: pd.DataFrame,
    extra_data: dict,
    label_column: str,
    plots_dest: str,
    problem_type: str,
):
    """
    Create and log an imbalance class artifact (csv + plot)
    """
    if label_column:
        if problem_type == "classification":
            labels_count = df[label_column].value_counts().sort_index()
            df_labels_count = pd.DataFrame(labels_count)
            df_labels_count.rename(columns={label_column: "Total"}, inplace=True)
            df_labels_count[label_column] = labels_count.index
            df_labels_count["weights"] = df_labels_count["Total"] / sum(
                df_labels_count["Total"]
            )

            fig = px.pie(df_labels_count, names=label_column, values="Total")
        else:
            fig = px.histogram(
                histfunc="count",
                x=df[label_column],
            )
            hist = np.histogram(df[label_column])
            df_labels_count = pd.DataFrame(
                {"min_val": hist[1], "count": hist[0].tolist() + [0]}
            )
        fig.update_layout(title_text="<i><b>Labels Imbalance</b></i>")
        extra_data["imbalance"] = context.log_artifact(
            PlotlyArtifact(key="imbalance", figure=fig),
            local_path=f"{plots_dest}/imbalance.html",
        )
        extra_data["imbalance-csv"] = context.log_artifact(
            TableArtifact("imbalance-weights-vec", df=df_labels_count),
            local_path=f"{plots_dest}/imbalance-weights-vec.csv",
        )


def _create_corr_artifact(
    context: MLClientCtx,
    df: pd.DataFrame,
    extra_data: dict,
    label_column: str,
    plots_dest: str,
):
    """
    Create and log an correlation-matrix artifact (csv + plot)
    """
    if label_column is not None:
        df = df.drop([label_column], axis=1)
    tblcorr = df.corr()
    extra_data["correlation-matrix-csv"] = context.log_artifact(
        TableArtifact("correlation-matrix-csv", df=tblcorr, visible=True),
        local_path=f"{plots_dest}/correlation-matrix.csv",
    )

    z = tblcorr.values.tolist()
    z_text = [["{:.2f}".format(y) for y in x] for x in z]
    fig = ff.create_annotated_heatmap(
        z,
        x=list(tblcorr.columns),
        y=list(tblcorr.columns),
        annotation_text=z_text,
        colorscale="agsunset",
    )
    fig["layout"]["yaxis"]["autorange"] = "reversed"  # l -> r
    fig.update_layout(title_text="<i><b>Correlation matrix</b></i>")
    fig["data"][0]["showscale"] = True

    extra_data["correlation"] = context.log_artifact(
        PlotlyArtifact(key="correlation", figure=fig),
        local_path=f"{plots_dest}/correlation.html",
    )
