""" Tests for the Deep explainer.
"""


import numpy as np
import pandas as pd
import pytest
from packaging import version

import shap
from shap import DeepExplainer

#os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

############################
# Tensorflow related tests #
############################

def test_tf_eager(random_seed):
    """ This is a basic eager example from keras.
    """
    tf = pytest.importorskip('tensorflow')

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    if version.parse(tf.__version__) >= version.parse("2.4.0"):
        pytest.skip("Deep explainer does not work for TF 2.4 in eager mode.")

    x = pd.DataFrame({"B": rs.random(size=(100,))})
    y = x.B
    y = y.map(lambda zz: chr(int(zz * 2 + 65))).str.get_dummies()

    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.Dense(10, input_shape=(x.shape[1],), activation="relu"))
    model.add(tf.keras.layers.Dense(y.shape[1], input_shape=(10,), activation="softmax"))
    model.summary()
    model.compile(loss="categorical_crossentropy", optimizer="Adam")
    model.fit(x.values, y.values, epochs=2)

    e = DeepExplainer(model, x.values[:1])
    sv = e.shap_values(x.values)
    assert np.abs(e.expected_value[0] + sv[0].sum(-1) - model(x.values)[:, 0]).max() < 1e-4


def test_tf_keras_mnist_cnn(random_seed):
    """ This is the basic mnist cnn example from keras.
    """
    tf = pytest.importorskip('tensorflow')
    rs = np.random.RandomState(random_seed)
    tf.compat.v1.random.set_random_seed(random_seed)

    from tensorflow import keras
    from tensorflow.compat.v1 import ConfigProto, InteractiveSession
    from tensorflow.keras import backend as K
    from tensorflow.keras.layers import (
        Activation,
        Conv2D,
        Dense,
        Dropout,
        Flatten,
        MaxPooling2D,
    )
    from tensorflow.keras.models import Sequential

    config = ConfigProto()
    config.gpu_options.allow_growth = True
    sess = InteractiveSession(config=config)

    tf.compat.v1.disable_eager_execution()

    batch_size = 64
    num_classes = 10
    epochs = 1

    # input image dimensions
    img_rows, img_cols = 28, 28

    # the data, split between train and test sets
    # (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
    x_train = rs.randn(200, 28, 28)
    y_train = rs.randint(0, 9, 200)
    x_test = rs.randn(200, 28, 28)
    y_test = rs.randint(0, 9, 200)

    if K.image_data_format() == 'channels_first':
        x_train = x_train.reshape(x_train.shape[0], 1, img_rows, img_cols)
        x_test = x_test.reshape(x_test.shape[0], 1, img_rows, img_cols)
        input_shape = (1, img_rows, img_cols)
    else:
        x_train = x_train.reshape(x_train.shape[0], img_rows, img_cols, 1)
        x_test = x_test.reshape(x_test.shape[0], img_rows, img_cols, 1)
        input_shape = (img_rows, img_cols, 1)

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    # convert class vectors to binary class matrices
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    model = Sequential()
    model.add(Conv2D(2, kernel_size=(3, 3),
                     activation='relu',
                     input_shape=input_shape))
    model.add(Conv2D(4, (3, 3), activation='relu'))
    model.add(MaxPooling2D(pool_size=(2, 2)))
    model.add(Dropout(0.25))
    model.add(Flatten())
    model.add(Dense(16, activation='relu')) # 128
    model.add(Dropout(0.5))
    model.add(Dense(num_classes))
    model.add(Activation('softmax'))

    model.compile(loss=keras.losses.categorical_crossentropy,
                  optimizer=keras.optimizers.legacy.Adadelta(),
                  metrics=['accuracy'])

    model.fit(x_train[:10, :], y_train[:10, :],
              batch_size=batch_size,
              epochs=epochs,
              verbose=1,
              validation_data=(x_test[:10, :], y_test[:10, :]))

    # explain by passing the tensorflow inputs and outputs
    inds = rs.choice(x_train.shape[0], 3, replace=False)
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].input), x_train[inds, :, :])
    shap_values = e.shap_values(x_test[:1])

    diff = sess.run(model.layers[-1].input, feed_dict={model.layers[0].input: x_test[:1]}) - \
    sess.run(model.layers[-1].input, feed_dict={model.layers[0].input: x_train[inds, :, :]}).mean(0)

    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    d = np.abs(sums - diff).sum()
    assert d / np.abs(diff).sum() < 0.001, "Sum of SHAP values does not match difference! %f" % d
    sess.close()

@pytest.mark.parametrize("activation", ["relu", "elu", "selu"])
def test_tf_keras_activations(activation):
    """Test verifying that a linear model with linear data gives the correct result.
    """

    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0

    tf = pytest.importorskip('tensorflow')

    from tensorflow.keras.layers import Dense, Input
    from tensorflow.keras.models import Model
    from tensorflow.keras.optimizers.legacy import SGD

    tf.compat.v1.disable_eager_execution()

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    # coefficients relating y with x1 and x2.
    coef = np.array([1, 2]).T

    # generate data following a linear relationship
    x = rs.normal(1, 10, size=(1000, len(coef)))
    y = np.dot(x, coef) + 1 + rs.normal(scale=0.1, size=1000)

    # create a linear model
    inputs = Input(shape=(2,))
    preds = Dense(1, activation=activation)(inputs)

    model = Model(inputs=inputs, outputs=preds)
    model.compile(optimizer=SGD(), loss='mse', metrics=['mse'])
    model.fit(x, y, epochs=30, shuffle=False, verbose=0)

    # explain
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].output), x)
    shap_values = e.shap_values(x)
    preds = model.predict(x)

    # verify that the explanation follows the equation in LinearExplainer
    values = shap_values[0] # since this is a "multi-output" model with one output

    assert values.shape == (1000, 2)
    np.allclose(values.sum(axis=1) + e.expected_value, preds[:, 0], atol=1e-5)



def test_tf_keras_linear():
    """Test verifying that a linear model with linear data gives the correct result.
    """

    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0

    tf = pytest.importorskip('tensorflow')

    from tensorflow.keras.layers import Dense, Input
    from tensorflow.keras.models import Model
    from tensorflow.keras.optimizers.legacy import SGD

    tf.compat.v1.disable_eager_execution()

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    # coefficients relating y with x1 and x2.
    coef = np.array([1, 2]).T

    # generate data following a linear relationship
    x = rs.normal(1, 10, size=(1000, len(coef)))
    y = np.dot(x, coef) + 1 + rs.normal(scale=0.1, size=1000)

    # create a linear model
    inputs = Input(shape=(2,))
    preds = Dense(1, activation='linear')(inputs)

    model = Model(inputs=inputs, outputs=preds)
    model.compile(optimizer=SGD(), loss='mse', metrics=['mse'])
    model.fit(x, y, epochs=30, shuffle=False, verbose=0)

    fit_coef = model.layers[1].get_weights()[0].T[0]

    # explain
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].output), x)
    shap_values = e.shap_values(x)

    # verify that the explanation follows the equation in LinearExplainer
    values = shap_values[0] # since this is a "multi-output" model with one output

    assert values.shape == (1000, 2)

    expected = (x - x.mean(0)) * fit_coef
    np.testing.assert_allclose(expected - values, 0, atol=1e-5)


def test_tf_keras_imdb_lstm(random_seed):
    """ Basic LSTM example using the keras API defined in tensorflow
    """
    tf = pytest.importorskip('tensorflow')
    rs = np.random.RandomState(random_seed)
    tf.compat.v1.random.set_random_seed(random_seed)

    # this fails right now for new TF versions (there is a warning in the code for this)
    if version.parse(tf.__version__) >= version.parse("2.5.0"):
        pytest.skip()

    from tensorflow.keras.datasets import imdb
    from tensorflow.keras.layers import LSTM, Dense, Embedding
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.preprocessing import sequence

    tf.compat.v1.disable_eager_execution()

    # load the data from keras
    max_features = 1000
    try:
        (X_train, _), (X_test, _) = imdb.load_data(num_words=max_features)
    except Exception:
        return # this hides a bug in the most recent version of keras that prevents data loading
    X_train = sequence.pad_sequences(X_train, maxlen=100)
    X_test = sequence.pad_sequences(X_test, maxlen=100)

    # create the model. note that this is model is very small to make the test
    # run quick and we don't care about accuracy here
    mod = Sequential()
    mod.add(Embedding(max_features, 8))
    mod.add(LSTM(10, dropout=0.2, recurrent_dropout=0.2))
    mod.add(Dense(1, activation='sigmoid'))
    mod.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

    # select the background and test samples
    inds = rs.choice(X_train.shape[0], 3, replace=False)
    background = X_train[inds]
    testx = X_test[10:11]

    # explain a prediction and make sure it sums to the difference between the average output
    # over the background samples and the current output
    sess = tf.compat.v1.keras.backend.get_session()
    sess.run(tf.compat.v1.global_variables_initializer())
    # For debugging, can view graph:
    # writer = tf.compat.v1.summary.FileWriter("c:\\tmp", sess.graph)
    # writer.close()
    e = shap.DeepExplainer((mod.layers[0].input, mod.layers[-1].output), background)
    shap_values = e.shap_values(testx)
    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    diff = sess.run(mod.layers[-1].output, feed_dict={mod.layers[0].input: testx})[0, :] - \
        sess.run(mod.layers[-1].output, feed_dict={mod.layers[0].input: background}).mean(0)
    assert np.allclose(sums, diff, atol=1e-02), "Sum of SHAP values does not match difference!"


#######################
# Torch related tests #
#######################

def _torch_cuda_available():
    """ Checks whether cuda is available. If so, torch-related tests are also tested on gpu.
    """
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        pass

    return False


TORCH_DEVICES = [
                    "cpu",
                    pytest.param(
                        "cuda",
                        marks=pytest.mark.skipif(not _torch_cuda_available(), reason="cuda unavailable (with torch)")
                    ),
]


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
@pytest.mark.parametrize("interim", [True, False])
def test_pytorch_mnist_cnn(torch_device, interim):
    """The same test as above, but for pytorch
    """
    torch = pytest.importorskip('torch')

    from torch import nn
    from torch.nn import functional as F

    class RandData:
        """ Random test data.
        """
        def __init__(self, batch_size):
            self.current = 0
            self.batch_size = batch_size

        def __iter__(self):
            return self

        def __next__(self):
            self.current += 1
            if self.current < 10:
                return torch.randn(self.batch_size, 1, 28, 28), torch.randint(0, 9, (self.batch_size,))
            raise StopIteration


    class Net(nn.Module):
        """ Basic conv net.
        """

        def __init__(self):
            super().__init__()
            # Testing several different activations
            self.conv_layers = nn.Sequential(
                nn.Conv2d(1, 10, kernel_size=5),
                nn.MaxPool2d(2),
                nn.Tanh(),
                nn.Conv2d(10, 20, kernel_size=5),
                nn.ConvTranspose2d(20, 20, 1),
                nn.AdaptiveAvgPool2d(output_size=(4, 4)),
                nn.Softplus(),
            )
            self.fc_layers = nn.Sequential(
                nn.Linear(320, 50),
                nn.BatchNorm1d(50),
                nn.ReLU(),
                nn.Linear(50, 10),
                nn.ELU(),
                nn.Softmax(dim=1)
            )

        def forward(self, x):
            """ Run the model.
            """
            x = self.conv_layers(x)
            x = x.view(-1, 320)
            x = self.fc_layers(x)
            return x


    def train(model, device, train_loader, optimizer, _, cutoff=20):
        model.train()
        num_examples = 0
        for _, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output, torch.eye(10).to(device)[target])

            loss.backward()
            optimizer.step()

            if num_examples > cutoff:
                break


    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 42

    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    batch_size = 32

    train_loader = RandData(batch_size)
    test_loader = RandData(batch_size)

    model = Net()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.5)

    device = torch.device(torch_device)

    model.to(device)
    train(model, device, train_loader, optimizer, 1)

    next_x, _ = next(iter(train_loader))
    inds = rs.choice(next_x.shape[0], 3, replace=False)

    next_x_random_choices = next_x[inds, :, :, :].to(device)

    if interim:
        e = shap.DeepExplainer((model, model.conv_layers[0]), next_x_random_choices)
    else:
        e = shap.DeepExplainer(model, next_x_random_choices)

    test_x, _ = next(iter(test_loader))
    input_tensor = test_x[:1].to(device)
    shap_values = e.shap_values(input_tensor)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        diff = (model(input_tensor) - model(next_x_random_choices)).detach().cpu().numpy().mean(0)

    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    d = np.abs(sums - diff).sum() / np.abs(diff).sum()

    assert d < 0.001, f"Sum of SHAP values does not match difference! {d}"


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
def test_pytorch_custom_nested_models(torch_device):
    """Testing single outputs
    """
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset

    class CustomNet1(nn.Module):
        """ Model 1.
        """
        def __init__(self, num_features):
            super().__init__()
            self.net = nn.Sequential(
                nn.Sequential(
                    nn.Conv1d(1, 1, 1),
                    nn.ConvTranspose1d(1, 1, 1),
                ),
                nn.AdaptiveAvgPool1d(output_size=num_features // 2),
            )

        def forward(self, X):
            """ Run the model.
            """
            return self.net(X.unsqueeze(1)).squeeze(1)

    class CustomNet2(nn.Module):
        """ Model 2.
        """
        def __init__(self, num_features):
            super().__init__()
            self.net = nn.Sequential(
                nn.LeakyReLU(),
                nn.Linear(num_features // 2, 2)
            )

        def forward(self, X):
            """ Run the model.
            """
            return self.net(X).unsqueeze(1)

    class CustomNet(nn.Module):
        """ Model 3.
        """
        def __init__(self, num_features):
            super().__init__()
            self.net1 = CustomNet1(num_features)
            self.net2 = CustomNet2(num_features)
            self.maxpool2 = nn.MaxPool1d(kernel_size=2)

        def forward(self, X):
            """ Run the model.
            """
            x = self.net1(X)
            return self.maxpool2(self.net2(x)).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                    epoch, batch_idx * len(data), len(train_loader.dataset),
                    100. * batch_idx / len(train_loader), loss.item()))


    random_seed = 777  # TODO: #2960

    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]

    data = TensorDataset(
                torch.tensor(X).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = CustomNet(num_features)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x, _ = next(iter(loader))

    inds = rs.choice(next_x.shape[0], 20, replace=False)

    next_x_random_choices = next_x[inds, :].to(device)
    e = shap.DeepExplainer(model, next_x_random_choices)

    test_x_tmp, _ = next(iter(loader))
    test_x = test_x_tmp[:1].to(device)

    shap_values = e.shap_values(test_x)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        diff = (model(test_x) - model(next_x_random_choices)).detach().cpu().numpy().mean(0)

    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    d = np.abs(sums - diff).sum() / np.abs(diff).sum()

    assert d < 0.001, f"Sum of SHAP values does not match difference! {d}"


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
def test_pytorch_single_output(torch_device):
    """Testing single outputs
    """
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset

    class Net(nn.Module):
        """ Test model.
        """
        def __init__(self, num_features):
            super().__init__()
            self.linear = nn.Linear(num_features // 2, 2)
            self.conv1d = nn.Conv1d(1, 1, 1)
            self.convt1d = nn.ConvTranspose1d(1, 1, 1)
            self.leaky_relu = nn.LeakyReLU()
            self.aapool1d = nn.AdaptiveAvgPool1d(output_size=num_features // 2)
            self.maxpool2 = nn.MaxPool1d(kernel_size=2)

        def forward(self, X):
            """ Run the model.
            """
            x = self.aapool1d(self.convt1d(self.conv1d(X.unsqueeze(1)))).squeeze(1)
            return self.maxpool2(self.linear(self.leaky_relu(x)).unsqueeze(1)).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                    epoch, batch_idx * len(data), len(train_loader.dataset),
                    100. * batch_idx / len(train_loader), loss.item()))


    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0
    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]

    data = TensorDataset(
                torch.tensor(X).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = Net(num_features)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x, _ = next(iter(loader))
    inds = rs.choice(next_x.shape[0], 20, replace=False)

    next_x_random_choices = next_x[inds, :].to(device)

    e = shap.DeepExplainer(model, next_x_random_choices)
    test_x_tmp, _ = next(iter(loader))
    test_x = test_x_tmp[:1].to(device)

    shap_values = e.shap_values(test_x)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        diff = (model(test_x) - model(next_x_random_choices)).detach().cpu().numpy().mean(0)

    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    d = np.abs(sums - diff).sum()  / np.abs(diff).sum()

    assert d < 0.001, f"Sum of SHAP values does not match difference! {d}"




@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
@pytest.mark.parametrize("disconnected", [True, False])
def test_pytorch_multiple_inputs(torch_device, disconnected):
    """ Check a multi-input scenario.
    """
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset


    class Net(nn.Module):
        """ Testing model.
        """
        def __init__(self, num_features, disconnected):
            super().__init__()
            self.disconnected = disconnected
            if disconnected:
                num_features = num_features // 2
            self.linear = nn.Linear(num_features, 2)
            self.output = nn.Sequential(
                nn.MaxPool1d(2),
                nn.ReLU()
            )

        def forward(self, x1, x2):
            """ Run the model.
            """
            if self.disconnected:
                x = self.linear(x1).unsqueeze(1)
            else:
                x = self.linear(torch.cat((x1, x2), dim=-1)).unsqueeze(1)
            return self.output(x).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data1, data2, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data1, data2, target = data1.to(device), data2.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data1, data2)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                    epoch, batch_idx * len(data), len(train_loader.dataset),
                    100. * batch_idx / len(train_loader), loss.item()))

    random_seed = 42  # TODO: 2960
    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]
    x1 = X[:, num_features // 2:]
    x2 = X[:, :num_features // 2]

    data = TensorDataset(
                torch.tensor(x1).float(),
                torch.tensor(x2).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = Net(num_features, disconnected)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x1, next_x2, _ = next(iter(loader))
    inds = rs.choice(next_x1.shape[0], 20, replace=False)
    background = [next_x1[inds, :].to(device), next_x2[inds, :].to(device)]
    e = shap.DeepExplainer(model, background)

    test_x1_tmp, test_x2_tmp, _ = next(iter(loader))
    test_x1 = test_x1_tmp[:1].to(device)
    test_x2 = test_x2_tmp[:1].to(device)

    shap_x1, shap_x2 = e.shap_values([test_x1[:1], test_x2[:1]])

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        diff = (model(test_x1, test_x2[:1]) - model(*background)).detach().cpu().numpy().mean(0)

    sums = np.array([shap_x1[i].sum() + shap_x2[i].sum() for i in range(len(shap_x1))])
    d = np.abs(sums - diff).sum() / np.abs(diff).sum()

    assert d < 0.001, f"Sum of SHAP values does not match difference! {d}"
