from __future__ import print_function, division

from keras.datasets import mnist
from keras.layers.merge import _Merge
from keras.layers import Input, Dense, Reshape, Flatten, Dropout
from keras.layers import BatchNormalization, Activation, ZeroPadding2D
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Sequential, Model
from keras.optimizers import RMSprop
from functools import partial

import keras.backend as K
from glob import glob
import matplotlib.pyplot as plt

import sys

import numpy as np

from keras.models import load_model



class RandomWeightedAverage(_Merge):
    """Provides a (random) weighted average between real and generated image samples"""
    def _merge_function(self, inputs):
        weights = K.random_uniform((32, 1, 1, 1))
        return (weights * inputs[0]) + ((1 - weights) * inputs[1])

class ImprovedWGAN():
    def __init__(self):
        self.img_rows = 72
        self.img_cols = 72
        self.channels = 1
        self.img_shape = (self.img_rows, self.img_cols, self.channels)

        # Following parameter and optimizer set as recommended in paper
        self.n_critic = 5
        optimizer = RMSprop(lr=0.00005)

        # Build the generator and discriminator
        # self.generator = self.build_generator()
        class RandomWeightedAverage(_Merge):
            """Provides a (random) weighted average between real and generated image samples"""
            def _merge_function(self, inputs):
                weights = K.random_uniform((32, 1, 1, 1))
                return (weights * inputs[0]) + ((1 - weights) * inputs[1])
        
        def gradient_penalty_loss(self, y_true, y_pred, averaged_samples):
            """
            Computes gradient penalty based on prediction and weighted real / fake samples
            """
            gradients = K.gradients(y_pred, averaged_samples)[0]
            # compute the euclidean norm by squaring ...
            gradients_sqr = K.square(gradients)
            #   ... summing over the rows ...
            gradients_sqr_sum = K.sum(gradients_sqr, axis=np.arange(1, len(gradients_sqr.shape)))
            #   ... and sqrt
            gradient_l2_norm = K.sqrt(gradients_sqr_sum)
            # compute lambda * (1 - ||grad||)^2 still for each single sample
            gradient_penalty = K.square(1 - gradient_l2_norm)
            # return the mean as loss over all the batch samples
            return K.mean(gradient_penalty)

        def wasserstein_loss(y_true, y_pred):
            return K.mean(y_true * y_pred)


        #self.generator = load_model('/saved_model/1000_generator_epoch.hdf5', custom_objects = {'wasserstein_loss' : wasserstein_loss})

        #self.discriminator = load_model('/saved_model/1000_discriminator_epoch.hdf5', custom_objects = {'wasserstein_loss' : wasserstein_loss})

        #-------------------------------
        # Construct Computational Graph
        #       for Discriminator
        #-------------------------------

        # Freeze generator's layers while training discriminator
        self.generator.trainable = False

        # Image input (real sample)
        real_img = Input(shape=self.img_shape)

        # Noise input
        z_disc = Input(shape=(100,))
        # Generate image based of noise (fake sample)
        fake_img = self.generator(z_disc)

        # Discriminator determines validity of the real and fake images
        fake = self.discriminator(fake_img)
        real = self.discriminator(real_img)

        # Construct weighted average between real and fake images
        merged_img = RandomWeightedAverage()([real_img, fake_img])
        # Determine validity of weighted sample
        valid_merged = self.discriminator(merged_img)

        # Use Python partial to provide loss function with additional
        # 'averaged_samples' argument
        partial_gp_loss = partial(self.gradient_penalty_loss, averaged_samples=merged_img)
        partial_gp_loss.__name__ = 'gradient_penalty' # Keras requires function names

        self.discriminator_model = Model(inputs=[real_img, z_disc], outputs=[real, fake, valid_merged])
        self.discriminator_model.compile(loss=[self.wasserstein_loss, self.wasserstein_loss, partial_gp_loss],optimizer=optimizer, loss_weights=[1, 1, 10])
        #-------------------------------
        # Construct Computational Graph
        #         for Generator
        #-------------------------------

        # For the generator we freeze the discriminator's layers
        self.discriminator.trainable = False
        self.generator.trainable = True

        # Sampled noise for input to generator
        z_gen = Input(shape=(100,))
        # Generate images based of noise
        img = self.generator(z_gen)
        # Discriminator determines validity
        valid = self.discriminator(img)
        # Defines generator model
        self.generator_model = Model(z_gen, valid)
        self.generator_model.compile(loss=self.wasserstein_loss, optimizer=optimizer)


    def gradient_penalty_loss(self, y_true, y_pred, averaged_samples):
        """
        Computes gradient penalty based on prediction and weighted real / fake samples
        """
        gradients = K.gradients(y_pred, averaged_samples)[0]
        # compute the euclidean norm by squaring ...
        gradients_sqr = K.square(gradients)
        #   ... summing over the rows ...
        gradients_sqr_sum = K.sum(gradients_sqr, axis=np.arange(1, len(gradients_sqr.shape)))
        #   ... and sqrt
        gradient_l2_norm = K.sqrt(gradients_sqr_sum)
        # compute lambda * (1 - ||grad||)^2 still for each single sample
        gradient_penalty = K.square(1 - gradient_l2_norm)
        # return the mean as loss over all the batch samples
        return K.mean(gradient_penalty)


    def wasserstein_loss(self, y_true, y_pred):
        return K.mean(y_true * y_pred)

    def build_generator(self):

        noise_shape = (100,)

        model = Sequential()
        s = 18
        model.add(Dense(128 * s * s, activation="relu", input_shape=noise_shape))
        model.add(Reshape((s, s, 128)))
        model.add(BatchNormalization(momentum=0.8))
        model.add(UpSampling2D())
        model.add(Conv2D(128, kernel_size=4, padding="same"))
        model.add(Activation("relu"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(UpSampling2D())
        model.add(Conv2D(64, kernel_size=4, padding="same"))
        model.add(Activation("relu"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Conv2D(self.channels, kernel_size=4, padding="same"))
        model.add(Activation("tanh"))

        model.summary()

        noise = Input(shape=noise_shape)
        img = model(noise)

        return Model(noise, img)

    def build_discriminator(self):

        img_shape = (self.img_rows, self.img_cols, self.channels)

        model = Sequential()

        model.add(Conv2D(16, kernel_size=3, strides=2, input_shape=img_shape, padding="same"))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(Conv2D(32, kernel_size=3, strides=2, padding="same"))
        model.add(ZeroPadding2D(padding=((0,1),(0,1))))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Conv2D(64, kernel_size=3, strides=2, padding="same"))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Conv2D(128, kernel_size=3, strides=1, padding="same"))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))

        model.add(Flatten())

        model.summary()

        img = Input(shape=img_shape)
        features = model(img)
        valid = Dense(1, activation="linear")(features)

        return Model(img, valid)

    def train(self, epochs, batch_size, sample_interval=50):

        # Load the dataset
        # (X_train, _), (_, _) = mnist.load_data()
        working_path = "../Detector/processDetectedNodules/output"
        
        file_list=glob(working_path+"*.npy")
        
        a = np.empty((72,72, 0), np.float64)
        print(a.shape)
        for img_file in file_list:

            img = np.load(img_file).astype(np.float64)
            # print("HI ", img.shape, "length:", img.shape[0])
            for i in range(0,img.shape[0]):
                a = np.dstack((a, img[i]))
            
        X_train = a.transpose()
        
        
        # Rescale -1 to 1
        X_train = (X_train.astype(np.float32) - 127.5) / 127.5
        X_train = np.expand_dims(X_train, axis=3)

        # Adversarial ground truths
        valid = -np.ones((batch_size, 1))
        fake =  np.ones((batch_size, 1))
        dummy = np.zeros((batch_size, 1)) # Dummy gt for gradient penalty
        for epoch in range(epochs):

            for _ in range(self.n_critic):

                # ---------------------
                #  Train Discriminator
                # ---------------------

                # Select a random batch of images
                idx = np.random.randint(0, X_train.shape[0], batch_size)
                imgs = X_train[idx]
                # Sample generator input
                noise = np.random.normal(0, 1, (batch_size, 100))
                # Train the discriminator
                d_loss = self.discriminator_model.train_on_batch([imgs, noise], [valid, fake, dummy])

            # ---------------------
            #  Train Generator
            # ---------------------

            # Sample generator input
            noise = np.random.normal(0, 1, (batch_size, 100))
            # Train the generator
            g_loss = self.generator_model.train_on_batch(noise, valid)

            # Plot the progress
            print ("%d [D loss: %f] [G loss: %f]" % (epoch, 1 - d_loss[0], 1 - g_loss))

            # If at save interval => save generated image samples
            if epoch % sample_interval == 0:
                self.generator.save('/saved_model/{}_generator_epoch.hdf5'.format(epoch))
                self.discriminator.save('/saved_model/{}_discriminator_epoch.hdf5'.format(epoch))
                self.sample_images(epoch)
#             self.sample_images(epoch)

    def sample_images(self, epoch):
        r, c = 5, 5
        noise = np.random.normal(0, 1, (r * c, 100))
        gen_imgs = self.generator.predict(noise)

        # Rescale images 0 - 1
        gen_imgs = 0.5 * gen_imgs + 1
        np.save("/output/gan_%d" % epoch, gen_imgs)
        #plt.imshow(gen_imgs)
        #plt.savefig("/output/mnist_%d.png" % epoch)
        #fig, axs = plt.subplots(r, c)
        #cnt = 0
        #for i in range(r):
        #    for j in range(c):
        #        axs[i,j].imshow(gen_imgs[cnt, :,:,0], cmap='gray')
        #        axs[i,j].axis('off')
        #        cnt += 1
                
        #fig.savefig("images/mnist_%d.png" % epoch)
        #plt.show()
        
if __name__ == '__main__':
    wgan = ImprovedWGAN()
    wgan.train(epochs=1001, batch_size=32, sample_interval=100)