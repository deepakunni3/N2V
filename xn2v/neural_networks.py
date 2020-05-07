from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import Dense, Input, Dropout, BatchNormalization, Activation, Concatenate, Layer
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.metrics import AUC
import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Union
from keras_tqdm import TQDMCallback, TQDMNotebookCallback
from environments_utils import is_notebook


class NeuralNetwork:
    def __init__(
        self,
        max_epochs: int = 1000,
        batch_size: int = 64,
        monitor: str = "auprc",
        patience: int = 10,
    ):
        """Instantiate a new NeuralNetwork.

            Parameters
            ----------------------
            max_epochs: int = 1000,
                Maximum number of epochs for which to train the model.
                It can be interrupted early by the early stopping.
            batch_size: int = 64,
                Number of samples to take in consideration for each batch.
            monitor: str = "auprc",
                Metric to monitor for the early stopping.
                It is possible to use validation metrics when training the model
                in contexts such as gaussian processes, where inner holdouts are used.
                Such metrics could be "val_auroc", "val_auprc" or "val_loss".
                Using validation metrics in non-inner holdouts is discouraged
                as it can be seen as epochs overfitting for the test set.
                When training the model on non-inner holdouts, use metrics
                such as "auroc", "auprc" or "loss".
            patience: int = 10,
                Number of epochs to wait for an improvement.
        """
        self._max_epochs = max_epochs
        self._batch_size = batch_size
        self._monitor = monitor
        self._patience = patience
        self._model = self._build_model()
        self._compile_model()

    def _build_model(self) -> Model:
        raise NotImplementedError(
            "The method _build_model has to be implemented in the subclasses."
        )

    def _compile_model(self) -> Model:
        self._model.compile(
            optimizer="nadam",
            loss="binary_crossentropy",
            metrics=[
                "accuracy",
                AUC(curve="ROC", name="auroc"),
                AUC(curve="PR", name="auroc")
            ]
        )

    def predict_proba(self, *args, **kwargs):
        return self._model.predict_proba(*args, **kwargs)

    def predict(self, *args, **kwargs):
        return self._model.predict(*args, **kwargs)

    def fit(
        self,
        train: Tuple[Union[Dict, List, np.ndarray]],
        test: Tuple[Union[Dict, List, np.ndarray]] = None
    ) -> pd.DataFrame:
        """Fit the model using given training parameters.

        Parameters
        --------------------------
        train: Tuple[Union[Dict, List, np.ndarray]],
            Either a tuple of list, np.ndarrays or dictionaries,
            containing the training data.
        test: Tuple[Union[Dict, List, np.ndarray]] = None
            Either a tuple of list, np.ndarrays or dictionaries,
            containing the validation data data.
            These data are optional, but they are required if
            the given monitor metric starts with "val_"

        Raises
        --------------------------
        ValueError,
            If no test data are given but the monitor metric
            starts with the word "val_", meaning it has to be
            computed on the test data.

        Returns
        ---------------------------
        The training history as a pandas dataframe.
        """
        if test is None and self._monitor.startswith("val_"):
            raise ValueError(
                "No test set was given, "
                "but a validation metric was required for the early stopping."
            )
        return pd.DataFrame(self._model.fit(
            *train,
            epochs=self._max_epochs,
            batch_size=self._batch_size,
            validation=test,
            verbose=False,
            shuffle=True,
            callbacks=[
                EarlyStopping(self._monitor, patience=self._patience),
                # We show the correct kind of callback depending if this
                # is running in a CLI or jupyter notebook-like environment.
                TQDMNotebookCallback() if is_notebook() else TQDMCallback()
            ]
        ).history)


class MLP(NeuralNetwork):

    def __init__(self, input_shape: Tuple, *args, **kwargs):
        self._input_shape = input_shape
        super().__init__(*args, **kwargs)

    def _build_model(self) -> Model:
        return Sequential([
            Input(self._input_shape),
            Dense(128, activation="relu"),
            Dense(128, activation="relu"),
            Dense(64, activation="relu"),
            Dense(32, activation="relu"),
            Dense(16, activation="relu"),
            Dense(1, activation="sigmoid"),
        ], name="MLP")


class FFNN(NeuralNetwork):

    def __init__(self, input_shape: Tuple, *args, **kwargs):
        self._input_shape = input_shape
        super().__init__(*args, **kwargs)

    def _build_model(self) -> Model:
        return Sequential([
            Input(self._input_shape),
            Dense(128, activation="relu"),
            Dense(128),
            BatchNormalization(),
            Activation("relu"),
            Dropout(0.3),
            Dense(64, activation="relu"),
            Dense(64, activation="relu"),
            BatchNormalization(),
            Activation("relu"),
            Dropout(0.3),
            Dense(32, activation="relu"),
            Dense(32, activation="relu"),
            BatchNormalization(),
            Activation("relu"),
            Dropout(0.3),
            Dense(16, activation="relu"),
            Dense(8, activation="relu"),
            Dense(1, activation="sigmoid"),
        ], name="FFNN")


class MultiModalFFNN(NeuralNetwork):

    def __init__(self, input_shape: Tuple, *args, **kwargs):
        self._input_shape = input_shape
        super().__init__(*args, **kwargs)

    def _sub_module(self, previous: Layer) -> Layer:
        hidden = Dense(128, activation="relu")(previous)
        hidden = Dense(128)(hidden)
        hidden = BatchNormalization()(hidden)
        hidden = Activation("relu")(hidden)
        hidden = Dropout(0.3)(hidden)
        hidden = Dense(64, activation="relu")(hidden)
        hidden = Dense(64, activation="relu")(hidden)
        hidden = BatchNormalization()(hidden)
        hidden = Activation("relu")(hidden)
        hidden = Dropout(0.3)(hidden)
        hidden = Dense(32, activation="relu")(hidden)
        hidden = Dense(32, activation="relu")(hidden)
        hidden = BatchNormalization()(hidden)
        hidden = Activation("relu")(hidden)
        return hidden

    def _build_model(self) -> Model:
        # Creating the two inputs
        left_input = Input(self._input_shape, name="left_input")
        right_input = Input(self._input_shape, name="right_input")

        # Build the left module
        left_module = self._sub_module(left_input)
        # Build the right module
        right_module = self._sub_module(right_input)

        # Concatenating the two modules
        middle = Concatenate()([left_module, right_module])

        # Creating the concatenation module
        hidden = Dropout(0.3)(middle)
        hidden = Dense(64, activation="relu")(hidden)
        hidden = Dense(64, activation="relu")(hidden)
        hidden = BatchNormalization()(hidden)
        hidden = Activation("relu")(hidden)
        hidden = Dropout(0.3)(hidden)
        hidden = Dense(32, activation="relu")(hidden)
        hidden = Dense(32, activation="relu")(hidden)
        hidden = BatchNormalization()(hidden)
        hidden = Activation("relu")(hidden)
        hidden = Dense(16, activation="relu")(hidden)
        hidden = Dense(8, activation="relu")(hidden)

        # Adding the model head
        head = Dense(1, activation="sigmoid")(hidden)

        # Building the multi-modal model.
        return Model(inputs=[left_input, right_input], outputs=head)

    def fit(
        self,
        left_input_train: Union[List, np.ndarray],
        right_input_train: Union[List, np.ndarray],
        output_train: Union[List, np.ndarray],
        left_input_test: Union[List, np.ndarray] = None,
        right_input_test: Union[List, np.ndarray] = None,
        output_test: Union[List, np.ndarray]=None
    ) -> pd.DataFrame:
        # Converting input values to the format
        # to be used for a multi-modal model.
        train = (
            {
                "left_input":left_input_train,
                "right_input":right_input_train
            },
            output_train
        )

        if all(d is not None for d in (left_input_test, right_input_test, output_test)):
            test = (
                {
                    "left_input":left_input_test,
                    "right_input":right_input_test
                },
                output_test
            )
        else:
            test = None
        
        return super().fit(train, test)
