import numpy as np
import keras.backend as K
from keras.layers import (Input, Dense, Reshape, Flatten, Lambda, merge,
                          Dropout, BatchNormalization, Activation, Embedding)
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import (UpSampling3D, Conv3D, ZeroPadding3D,
                                        AveragePooling3D)
from keras.models import Model, Sequential
import math
import tensorflow as tf

# calculate sum of intensities
def ecal_sum(image, daxis):
    sum = K.sum(image, axis=daxis)
    return sum

# angle calculation 
def ecal_angle(image, daxis):
    image = K.squeeze(image, axis=daxis)# squeeze along channel axis
    
    # get shapes
    x_shape= K.int_shape(image)[1]
    y_shape= K.int_shape(image)[2]
    z_shape= K.int_shape(image)[3]
    sumtot = K.sum(image, axis=(1, 2, 3))# sum of events

    # get 1. where event sum is 0 and 0 elsewhere
    amask = tf.where(K.equal(sumtot, 0.0), K.ones_like(sumtot) , K.zeros_like(sumtot))
    masked_events = K.sum(amask) # counting zero sum events
    
    # ref denotes barycenter as that is our reference point
    x_ref = K.sum(K.sum(image, axis=(2, 3)) * (K.cast(K.expand_dims(K.arange(x_shape), 0), dtype='float32') + 0.5), axis=1)# sum for x position * x index
    y_ref = K.sum(K.sum(image, axis=(1, 3)) * (K.cast(K.expand_dims(K.arange(y_shape), 0), dtype='float32') + 0.5), axis=1)
    z_ref = K.sum(K.sum(image, axis=(1, 2)) * (K.cast(K.expand_dims(K.arange(z_shape), 0), dtype='float32') + 0.5), axis=1)
    x_ref = tf.where(K.equal(sumtot, 0.0), K.ones_like(x_ref) , x_ref/sumtot)# return max position if sumtot=0 and divide by sumtot otherwise
    y_ref = tf.where(K.equal(sumtot, 0.0), K.ones_like(y_ref) , y_ref/sumtot)
    z_ref = tf.where(K.equal(sumtot, 0.0), K.ones_like(z_ref), z_ref/sumtot)
    #reshape    
    x_ref = K.expand_dims(x_ref, 1)
    y_ref = K.expand_dims(y_ref, 1)
    z_ref = K.expand_dims(z_ref, 1)

    sumz = K.sum(image, axis =(1, 2)) # sum for x,y planes going along z

    # Get 0 where sum along z is 0 and 1 elsewhere
    zmask = tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz) , K.ones_like(sumz))
        
    x = K.expand_dims(K.arange(x_shape), 0) # x indexes
    x = K.cast(K.expand_dims(x, 2), dtype='float32') + 0.5
    y = K.expand_dims(K.arange(y_shape), 0)# y indexes
    y = K.cast(K.expand_dims(y, 2), dtype='float32') + 0.5
  
    #barycenter for each z position
    x_mid = K.sum(K.sum(image, axis=2) * x, axis=1)
    y_mid = K.sum(K.sum(image, axis=1) * y, axis=1)
    x_mid = tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz), x_mid/sumz) # if sum != 0 then divide by sum
    y_mid = tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz), y_mid/sumz) # if sum != 0 then divide by sum

    #Angle Calculations
    z = (K.cast(K.arange(z_shape), dtype='float32') + 0.5)  * K.ones_like(z_ref) # Make an array of z indexes for all events
    zproj = K.sqrt(K.maximum((x_mid-x_ref)**2.0 + (z - z_ref)**2.0, K.epsilon()))# projection from z axis with stability check
    m = tf.where(K.equal(zproj, 0.0), K.zeros_like(zproj), (y_mid-y_ref)/zproj)# to avoid divide by zero for zproj =0
    m = tf.where(K.less(z, z_ref),  -1 * m, m)# sign inversion
    ang = (math.pi/2.0) - tf.atan(m)# angle correction
    zmask = tf.where(K.equal(zproj, 0.0), K.zeros_like(zproj) , zmask)
    ang = ang * zmask # place zero where zsum is zero
    
    ang = ang * z  # weighted by position
    sumz_tot = z * zmask # removing indexes with 0 energies or angles

    #zunmasked = K.sum(zmask, axis=1) # used for simple mean 
    #ang = K.sum(ang, axis=1)/zunmasked # Mean does not include positions where zsum=0

    ang = K.sum(ang, axis=1)/K.sum(sumz_tot, axis=1) # sum ( measured * weights)/sum(weights)
    ang = tf.where(K.equal(amask, 0.), ang, 100. * K.ones_like(ang)) # Place 100 for measured angle where no energy is deposited in events
    
    ang = K.expand_dims(ang, 1)
    return ang

def discriminator(power=1.0, dformat='channels_last'):
    # Keras backend format is implemented initially for setting
    # the channel
    K.set_image_data_format(dformat)
    if dformat =='channels_last':
        dshape=(51, 51, 25,1) # sample shape
        daxis=4 # channel axis 
        baxis=-1 # axis for BatchNormalization
        daxis2=(1, 2, 3) # axis for sum
    else:
        dshape=(1, 51, 51, 25) 
        daxis=1 
        baxis=1 
        daxis2=(2, 3, 4)
    image=Input(shape=dshape)

    # Example helper: build an ensemble of 16 3D convolutional layers
    # of shape (5, 6, 6) each with 0-padding across the borders. In this
    # way, dimensionality is not lost after filtering. Apply afterwards 
    # the acttivation function LeakyReLu and use a dropout of 0.2, meaning
    # that 20% of the neurons in the final stage will be inactive to avoid
    # overfitting
    x = Conv3D(16, (5, 6, 6), padding='same')(image)
    x = LeakyReLU()(x)
    x = Dropout(0.2)(x)

    # Now apply beforehand the zero-padding, and then 8 kernels of the same
    # size as before, and same activation function. Batch normalization is
    # also applied, meaning that all the images will be reset so the whole
    # sets do not diverge
    x = ZeroPadding3D((0, 0, 1))(x)
    x = Conv3D(8, (5, 6, 6), padding='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization(axis=baxis, epsilon=1e-6)(x)
    x = Dropout(0.2)(x)

    x = ZeroPadding3D((0, 0, 1))(x)
    x = Conv3D(8, (5, 6, 6), padding='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization(axis=baxis, epsilon=1e-6)(x)
    x = Dropout(0.2)(x)

    x = Conv3D(8, (5, 6, 6), padding='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization(axis=baxis, epsilon=1e-6)(x)
    x = Dropout(0.2)(x)

    # Make an average pooling of stride 2, hence the image shrinks
    # twice. This is harder to perform than the MaxPooling2D
    x = AveragePooling3D((2, 2, 2))(x)
    h = Flatten()(x)

    dnn = Model(image, h)
    dnn.summary()

    dnn_out = dnn(image)
    fake = Dense(1, activation='sigmoid', name='generation')(dnn_out)
    aux = Dense(1, activation='linear', name='auxiliary')(dnn_out)
    inv_image = Lambda(K.pow, arguments={'a':1./power})(image) #get back original image
    ang = Lambda(ecal_angle, arguments={'daxis':daxis})(inv_image) # angle calculation
    ecal = Lambda(ecal_sum, arguments={'daxis':daxis2})(inv_image) # sum of energies
    Model(inputs=[image], outputs=[fake, aux, ang, ecal]).summary()
    return Model(inputs=[image], outputs=[fake, aux, ang, ecal])


def generator(latent_size=256, return_intermediate=False, dformat='channels_last'):
    if dformat =='channels_last':
        dim = (9,9,8,8) # shape for dense layer
        baxis=-1 # axis for BatchNormalization
    else:
        dim = (8, 9, 9,8)
        baxis=1
    K.set_image_data_format(dformat)
    loc = Sequential([
        Dense(5184, input_shape=(latent_size,)),
        Reshape(dim),
        UpSampling3D(size=(6, 6, 6)),
        
        Conv3D(8, (6, 6, 8), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        
        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        ####################################### added layers 
        
        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),

        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),

        ZeroPadding3D((1, 1, 0)),
        Conv3D(6, (3, 3, 5), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        
        #####################################  
        
        ZeroPadding3D((1, 1,0)),
        Conv3D(6, (3, 3, 3), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        
        Conv3D(1, (2, 2, 2),  padding='valid', kernel_initializer='glorot_normal'),
        Activation('relu')
    ])
    latent = Input(shape=(latent_size, ))   
    fake_image = loc(latent)
    loc.summary()
    Model(inputs=[latent], outputs=[fake_image]).summary()
    return Model(inputs=[latent], outputs=[fake_image])

def main():
    dformat= 'channels_first'
    g= generator(dformat=dformat)
    d=discriminator(dformat=dformat)

if __name__ == "__main__":
    main()

                
