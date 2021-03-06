#Training for GAN

from __future__ import print_function
import os
## setting seed ###
#from numpy.random import seed
#seed(1)
#from tensorflow import set_random_seed
#set_random_seed(1)
#import random
#random.seed(1)
#os.environ['PYTHONHASHSEED'] = '0' 
##################

from collections import defaultdict
try:
    import cPickle as pickle
except ImportError:
    import pickle
import keras
import argparse
import sys
import h5py 
import numpy as np
import time
import math
import tensorflow as tf
# The command below makes use of the file GANUtils.py
import analysis.utils.GANutils as gan

if (str(".cern.ch") in str(os.environ.get('HOSTNAME'))): # Here a check for host can be used to set defaults accordingly
    tlab = True
else:
    tlab= False

    
try:
    import setGPU #if Caltech
except:
    pass

# Import the backend system of the keras library, as well as 
# all the keras libraries for models, layers and activation 
# functions
import keras.backend as K
from keras.layers import Input
from keras.models import Model
from keras.optimizers import Adadelta, Adam, RMSprop
from keras.utils.generic_utils import Progbar

def main():
    #Architectures to import
    from AngleArch3dGAN import generator, discriminator
    
    # Values to be set by user. They are built using the parser and
    # the argparser libraries. The specific ML parameters are set here-
    # number of epochs, size of a batch and number of minibatches, the
    # as well as the latent space size. Number of events and the datapath
    # are also set
    parser = get_parser()
    params = parser.parse_args()
    nb_epochs = params.nbepochs #Total Epochs
    batch_size = params.batchsize #batch size
    latent_size = params.latentsize #latent vector size
    verbose = params.verbose
    datapath = params.datapath# Data path
    outpath = params.outpath # training output
    nEvents = params.nEvents# maximum number of events used in training
    ascale = params.ascale # angle scale
    yscale = params.yscale # scaling energy
    weightdir = 'weights/3dgan_weights_' + params.name
    pklfile = 'results/3dgan_history_' + params.name + '.pkl'# loss history
    resultfile = 'results/3dgan_analysis' + params.name + '.pkl'# optimization metric history
    prev_gweights = 'weights/' + params.prev_gweights
    prev_dweights = 'weights/' + params.prev_dweights
    xscale = params.xscale
    xpower = params.xpower
    analyse=params.analyse # if analysing
    loss_weights=[params.gen_weight, params.aux_weight, params.ang_weight, params.ecal_weight]
    dformat=params.dformat
    thresh = params.thresh # threshold for data
    angtype = params.angtype
    particle = params.particle
    warm = params.warm
    lr = params.lr
    events_per_file = 5000
    energies = [0, 110, 150, 190]

    # More cases are analysed to decide which datapath to use
    if tlab:
       if not warm:
         datapath = 'tlab'
       outpath = '/gkhattak/'
         
    if datapath=='reduced':
       # datapath = "/storage/group/gpu/bigdata/gkhattak/*Measured3ThetaEscan/*.h5"  # Data path 100-200 GeV    
       datapath = "/home/user/Documents/CERN/3Dgan/keras/results/*.h5"                                                    
    elif datapath=='full':
       datapath = "/storage/group/gpu/bigdata/LCDLargeWindow/LCDLargeWindow/varangle/*scan/*scan_RandomAngle_*.h5" # culture plate                              
       events_per_file = 10000
       energies = [0, 50, 100, 200, 250, 300, 400, 500]
    elif datapath=='eos':
       datapath = "/eos/user/g/gkhattak/VarAngleData/*Measured3ThetaEscan/*.h5"  # Data path 100-200 GeV                                             
    elif datapath=='tlab':
       datapath = "/gkhattak/data/*RandomAngle100GeV/*.h5"
       energies = [0, 10, 50, 90]
    else:
       datapath =datapath + "/*Measured3ThetaEscan/*.h5"
    weightdir = outpath + 'weights/3dgan_weights_' + params.name
    pklfile = outpath + 'results/3dgan_history_' + params.name + '.pkl'# loss history
    resultfile = outpath + 'results/3dgan_analysis' + params.name + '.pkl'# optimization metric history   
    prev_gweights = outpath + 'weights/' + params.prev_gweights
    prev_dweights = outpath + 'weights/' + params.prev_dweights

    print(datapath)
    print(params)
    
    # Building discriminator and generator. They are built using the AngleArch3dGAN
    # file, where the layers are set
    gan.safe_mkdir(weightdir)

    # Set up the discriminator and the generator using as input the following:
    # DISCRIMINATOR - one float number and first / last channel
    # GENERATOR - latent size space and first / last channel
    d=discriminator(xpower, dformat=dformat)
    g=generator(latent_size, dformat=dformat)
    
    # GAN training 
    Gan3DTrainAngle(d, g, datapath, nEvents, weightdir, pklfile, nb_epochs=nb_epochs, batch_size=batch_size,
                    latent_size=latent_size, loss_weights=loss_weights, lr=lr, xscale = xscale, xpower=xpower, angscale=ascale,
                    yscale=yscale, thresh=thresh, angtype=angtype, analyse=analyse, resultfile=resultfile,
                    energies=energies, dformat=dformat, particle=particle, verbose=verbose, warm=warm,
                    prev_gweights= prev_gweights, prev_dweights=prev_dweights   )

# Below is the function for setting the parser for reading the parameters
def get_parser():
    parser = argparse.ArgumentParser(description='3D GAN Params' )
    parser.add_argument('--nbepochs', action='store', type=int, default=120, help='Number of epochs to train for.')
    parser.add_argument('--batchsize', action='store', type=int, default=64, help='batch size per update')
    parser.add_argument('--latentsize', action='store', type=int, default=256, help='size of random N(0, 1) latent space to sample')
    parser.add_argument('--datapath', action='store', type=str, default='reduced', help='HDF5 files to train from.')
    parser.add_argument('--outpath', action='store', type=str, default='', help='Dir to save output from a training.')
    parser.add_argument('--dformat', action='store', type=str, default='channels_last')
    parser.add_argument('--nEvents', action='store', type=int, default=400000, help='Maximum Number of events used for Training')
    parser.add_argument('--verbose', action='store_true', help='Whether or not to use a progress bar')
    parser.add_argument('--xscale', action='store', type=int, default=1, help='Multiplication factor for ecal deposition')
    parser.add_argument('--xpower', action='store', type=float, default=0.85, help='pre processing of cell energies by raising to a power')
    parser.add_argument('--yscale', action='store', type=int, default=100, help='Division Factor for Primary Energy.')
    parser.add_argument('--ascale', action='store', type=int, default=1, help='Multiplication factor for angle input')
    parser.add_argument('--analyse', action='store', default=False, help='Whether or not to perform analysis')
    parser.add_argument('--gen_weight', action='store', type=float, default=3, help='loss weight for generation real/fake loss')
    parser.add_argument('--aux_weight', action='store', type=float, default=0.1, help='loss weight for auxilliary energy regression loss')
    parser.add_argument('--ang_weight', action='store', type=float, default=25, help='loss weight for angle loss')
    parser.add_argument('--ecal_weight', action='store', type=float, default=0.1, help='loss weight for ecal sum loss')
    parser.add_argument('--hist_weight', action='store', type=float, default=0.1, help='loss weight for additional bin count loss')
    parser.add_argument('--thresh', action='store', type=int, default=0., help='Threshold for cell energies')
    parser.add_argument('--angtype', action='store', type=str, default='mtheta', help='Angle to use for Training. It can be theta, mtheta or eta')
    parser.add_argument('--particle', action='store', type=str, default='Ele', help='Type of particle')
    parser.add_argument('--lr', action='store', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--warm', action='store', default=False, help='Start from pretrained weights or random initialization')
    parser.add_argument('--prev_gweights', type=str, default='3dgan_weights__remove_bin/params_generator_epoch_111.hdf5', help='Initial generator weights for warm start')
    parser.add_argument('--prev_dweights', type=str, default='3dgan_weights__remove_bin/params_discriminator_epoch_111.hdf5', help='Initial discriminator weights for warm start')
    parser.add_argument('--name', action='store', type=str, default='training', help='Unique identifier can be set for each training')
    return parser

# Get data for training
def GetDataAngle(datafile, xscale =1, xpower=1, yscale = 100, angscale=1, angtype='theta', thresh=1e-4, daxis=-1):
    print ('Loading Data from .....', datafile)
    f=h5py.File(datafile,'r')
    X=np.array(f.get('ECAL'))* xscale
    Y=np.array(f.get('energy'))/yscale
    X[X < thresh] = 0
    X = X.astype(np.float32)
    print("Initial shape of X matrix is: {}".format(X.shape))
    Y = Y.astype(np.float32)
    ecal = np.sum(X, axis=(1, 2, 3))
    indexes = np.where(ecal > 10.0)
    X=X[indexes]
    Y=Y[indexes]
    if angtype in f:
      ang = np.array(f.get(angtype))[indexes]
    else:
      ang = gan.measPython(X)
    X = np.expand_dims(X, axis=daxis)
    ecal=ecal[indexes]
    print("Shape of X matrix is: " + str(X.shape))
    # ecal=np.expand_dims(ecal, axis=daxis)
    ecal = ecal.reshape(X.shape[0], 1, 1, 1, 1)
    print("Shape of the ecal matrix: " + str(ecal.shape))
    if xpower !=1.:
        X = np.power(X, xpower)
    return X, Y, ang, ecal

# Function for setting up the training procedure for the network
def Gan3DTrainAngle(discriminator, generator, datapath, nEvents, WeightsDir, pklfile, nb_epochs=30, batch_size=20, latent_size=200, loss_weights=[3, 0.1, 25, 0.1, 0.1], lr=0.001, rho=0.9, decay=0.0, g_weights='params_generator_epoch_', d_weights='params_discriminator_epoch_', xscale=1, xpower=1, angscale=1, angtype='theta', yscale=100, thresh=1e-4, analyse=False, resultfile="", energies=[], dformat='channels_last', particle='Ele', verbose=False, warm=False, prev_gweights='', prev_dweights=''):
    start_init = time.time()
    # The above list represents the fractions taken for the
    # train and test data. For (0.5, 0.5) 
    f = [0.5, 0.5] 
    
    # Apply settings according to data format -> set the axis for
    # element-wise summing as function of the channel for use
    if dformat=='channels_last':
        # Implement the channel axis and the axis for sum
       daxis=4
       daxis2=(1, 2, 3) 
    else:
        # The same procedures as above
       daxis=1
       daxis2=(2, 3, 4) 

    # Build the discriminator. Printing statement is implemented as
    # testing, and then the compliling method is used
    print('[INFO] Building discriminator')
    # Keras library is implemented for compiling the discriminator.
    # The optimizer is given by the Root Mean Square propagation, and
    # the loss function takes the values specified below.
    discriminator.compile(
        optimizer=RMSprop(lr),
        loss=['binary_crossentropy', 'mean_absolute_percentage_error', 'mae', 'mean_absolute_percentage_error'],
        loss_weights=loss_weights
    )

    # Build the generator. Printing statement and compiling method
    # are once again implemented. The OPTIMIZER represents the method
    # used for achieving global minima - example: GD, SGD, mini-batch
    # SGD, etc. The loss function represents the quantity to minimize 
    # example: quadratic, binary cross-entropy, etc.
    print('[INFO] Building generator')
    generator.compile(
        optimizer=RMSprop(lr),
        loss='binary_crossentropy'
    )
 
    # Build combined Model. Introduce the latent space and
    # generate a fake image with the latent size specified
    latent = Input(shape=(latent_size, ), name='combined_z')   
    fake_image = generator(latent)
    discriminator.trainable = False

    # Now return the fake image, as well as the angle and 
    # energy computed from the discriminator. Afterwards 
    # create the model with input from latent space and 
    # output specified by the fake image, as well as the 
    # angle and energy deposited.= in calorimeter.
    fake, aux, ang, ecal= discriminator(fake_image)
    combined = Model(
        inputs=[latent],
        outputs=[fake, aux, ang, ecal],
        name='combined_model'
    )
    combined.compile(
        optimizer=RMSprop(lr),
        loss=['binary_crossentropy', 'mean_absolute_percentage_error', 'mae', 'mean_absolute_percentage_error'],
        loss_weights=loss_weights
    )

    # From the input in the GetTrainDataAngle3D
    # function, the warm boolean variable is set to False.
    if warm:
        generator.load_weights(prev_gweights)
        print('Generator initialized from {}'.format(prev_gweights))
        discriminator.load_weights(prev_dweights)
        print('Discriminator initialized from {}'.format(prev_dweights))

    # Getting All available Data sorted in test train fraction. 
    # For this part, train and test data are divided using the 
    # two files given in the same directory.
    Trainfiles, Testfiles = gan.DivideFiles(datapath, f, datasetnames=["ECAL"], Particles =[particle])
    discriminator.trainable = True # to allow updates to moving averages for BatchNormalization     
    print(Trainfiles)
    print(Testfiles)
    
    # The number of test events calculated from fraction of nEvents
    # The number of train events calculated from fraction of nEvents
    nb_Test = int(nEvents * f[1]) 
    nb_Train = int(nEvents * f[0]) 

    # The number of actual batches used will be min(available batches & nb_Train)
    nb_train_batches = int(nb_Train/batch_size)
    nb_test_batches = int(nb_Test/batch_size)
    print('The max train batches can be {} batches while max test batches can be {}'.format(nb_train_batches, nb_test_batches))  
    train_history = defaultdict(list)
    test_history = defaultdict(list)
    init_time = time.time()- start_init
    analysis_history = defaultdict(list)
    print('Initialization time is {} seconds'.format(init_time))
    
    ###
    ### THIS PART CORRESPONDS TO THE TRAINING
    ###
    # Start training - go through each epoch and update the
    # weights and biases
    for epoch in range(nb_epochs):
        epoch_start = time.time()
        print('Epoch {} of {}'.format(epoch + 1, nb_epochs))

        # Read first file using the DataANgle function. This 
        # represents the equivalent in the scientific paper of
        # getting the real deposited energy and angle, as well as
        # the sum of energies
        X_train, Y_train, ang_train, ecal_train = GetDataAngle(Trainfiles[0], xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
        nb_file=1
        epoch_gen_loss = []
        epoch_disc_loss = []
        index = 0
        file_index=0
        
        # Repeat till training data is available
        while nb_file < len(Trainfiles) and index < nb_train_batches:
            if verbose:
                progress_bar.update(index)
            else:
                if index % 100 == 0:
                    print('processed {} batches'.format(index + 1))
            # Print helper statement
            print("Index used: {}".format(index))
            
            loaded_data = X_train.shape[0]
            used_data = file_index * batch_size
            # Check if loaded data is less than bacth size
            if (loaded_data - used_data) < (batch_size + 1 ):
                # Remove the batches used
                X_left = X_train[(file_index * batch_size):]
                Y_left = Y_train[(file_index * batch_size):]
                ang_left = ang_train[(file_index * batch_size):]
                ecal_left = ecal_train[(file_index * batch_size):]

                # Read in next file                                                
                X_train, Y_train, ang_train, ecal_train = GetDataAngle(Trainfiles[nb_file], xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
                nb_file+=1
                # Concatenate to left over data
                X_train = np.concatenate((X_left, X_train))
                Y_train = np.concatenate((Y_left, Y_train))
                ang_train = np.concatenate((ang_left, ang_train))
                ecal_train = np.concatenate((ecal_left, ecal_train))
                nb_batches = int(X_train.shape[0] / batch_size)
                print("{} batches loaded..........".format(nb_batches))
                file_index = 0

            # Get a single batch containing the whole analysis on ther  
            image_batch = X_train[(file_index * batch_size):(file_index  + 1) * batch_size]
            energy_batch = Y_train[(file_index * batch_size):(file_index + 1) * batch_size]
            ecal_batch = ecal_train[(file_index *  batch_size):(file_index + 1) * batch_size]
            ang_batch = ang_train[(file_index * batch_size):(file_index + 1) * batch_size]
            #add_loss_batch = np.expand_dims(loss_ftn(image_batch, xpower, daxis2), axis=-1)
            file_index +=1

            # Generate Fake events with same energy and angle as data batch. The commands
            # below yield the generation of noise from the latent size. This is highly 
            # necessary for the reproduction of random numbers which pass through the generator
            # and yield the fake image
            noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)

            # Now the energy deposited, the angle and the noise from the latent 
            # space are all concatenated. This represents the overall input towards 
            # the generator
            generator_ip = np.concatenate((energy_batch.reshape(-1, 1), ang_batch.reshape(-1, 1), noise), axis=1)

            # Now come the generated images after the ensemble of energy, angle and noise
            # from the latent space is sent through the layer of cnn neural nets
            generated_images = generator.predict(generator_ip, verbose=0)

            # Train discriminator first on real batch and then the fake batch
            real_batch_loss = discriminator.train_on_batch(image_batch, [gan.BitFlip(np.ones(batch_size).astype(np.float32)), energy_batch, ang_batch, ecal_batch])
            fake_batch_loss = discriminator.train_on_batch(generated_images, [gan.BitFlip(np.zeros(batch_size).astype(np.float32)), energy_batch, ang_batch, ecal_batch])

            #if ecal sum has 100% loss(generating empty events) then end the training 
            if fake_batch_loss[3] == 100.0 and index >10:
                print("Empty image with Ecal loss equal to 100.0 for {} batch".format(index))
                generator.save_weights(WeightsDir + '/{0}eee.hdf5'.format(g_weights), overwrite=True)
                discriminator.save_weights(WeightsDir + '/{0}eee.hdf5'.format(d_weights), overwrite=True)
                print ('real_batch_loss', real_batch_loss)
                print ('fake_batch_loss', fake_batch_loss)
                sys.exit()
            # append mean of discriminator loss for real and fake events 
            epoch_disc_loss.append([
                (a + b) / 2 for a, b in zip(real_batch_loss, fake_batch_loss)
            ])
            
            trick = np.ones(batch_size).astype(np.float32)
            gen_losses = []
            # Train generator twice using combined model
            for _ in range(2):

                # For two times implement again a different noise from the
                # latent space and concatenate it with the energies and the 
                # angles for obtaining the input for the generator
                noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)
                generator_ip = np.concatenate((energy_batch.reshape(-1, 1), ang_batch.reshape(-1, 1), noise), axis=1) # sampled angle same as g4 theta

                # Perform the training by maximizing the discriminator loss on 
                # the generated images 
                gen_losses.append(combined.train_on_batch(
                    [generator_ip],
                    [trick, energy_batch.reshape(-1, 1), ang_batch, ecal_batch]))
            
            generator_loss = [(a + b) / 2 for a, b in zip(*gen_losses)]
            epoch_gen_loss.append(generator_loss)
            index +=1

        ###
        ### THIS PART CORRESPONDS TO THE TESTING
        ###
        # Test process will also be accomplished in batches to reduce memory consumption
        print ('Total batches were {}'.format(index))
        print('Time taken by epoch{} was {} seconds.'.format(epoch, time.time()-epoch_start))
        print('\nTesting for epoch {}:'.format(epoch))
        test_start = time.time()

        # Read first test file
        X_test, Y_test, ang_test, ecal_test = GetDataAngle(Testfiles[0], xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
        disc_test_loss=[]
        gen_test_loss =[]
        nb_file=1
        index=0
        file_index=0
        # Repeat till data is available
        while nb_file < len(Testfiles) and index < nb_test_batches:
           loaded_data = X_test.shape[0]
           used_data = file_index * batch_size
           # if loaded test data has less a single batch
           if (loaded_data - used_data) < (batch_size + 1 ):
               # remove data already used
               X_left = X_test[(file_index * batch_size):]
               Y_left = Y_test[(file_index * batch_size):]
               ang_left = ang_test[(file_index * batch_size):]
               ecal_left = ecal_test[(file_index * batch_size):]
               # read in new file
               X_test, Y_test, ang_test, ecal_test = GetDataAngle(Testfiles[nb_file], xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
               nb_file+=1
               # concatenate with left over data
               X_test = np.concatenate((X_left, X_test))
               Y_test = np.concatenate((Y_left, Y_test))
               ang_test = np.concatenate((ang_left, ang_test))
               ecal_test = np.concatenate((ecal_left, ecal_test))
               nb_batches = int(X_train.shape[0] / batch_size)

               print("{} test batches loaded..........".format(nb_batches))
               file_index = 0
           # Get one batch
           image_batch = X_test[(file_index * batch_size):(file_index  + 1) * batch_size]
           energy_batch = Y_test[(file_index * batch_size):(file_index + 1) * batch_size]
           ecal_batch = ecal_test[(file_index *  batch_size):(file_index + 1) * batch_size]
           ang_batch = ang_test[(file_index * batch_size):(file_index + 1) * batch_size]
           #add_loss_batch = np.expand_dims(loss_ftn(image_batch, xpower, daxis2), axis=-1)
           file_index +=1

           # Generate fake events: The purpose now represents to evaluate the
           # discriminator on real and fake data                                                            
           noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)
           generator_ip = np.concatenate((energy_batch.reshape(-1, 1), ang_batch.reshape(-1, 1), noise), axis=1)
           generated_images = generator.predict(generator_ip, verbose=False)

           # Concatenate to fake and real batches
           X = np.concatenate((image_batch, generated_images))
           y = np.array([1] * batch_size + [0] * batch_size).astype(np.float32)
           ang = np.concatenate((ang_batch, ang_batch))
           ecal = np.concatenate((ecal_batch, ecal_batch))
           aux_y = np.concatenate((energy_batch, energy_batch), axis=0)
           index +=1

           # Evaluate discriminator loss           
           disc_test_loss.append(discriminator.evaluate( X, [y, aux_y, ang, ecal], verbose=False, batch_size=batch_size))
           # Evaluate generator loss
           gen_test_loss.append(combined.evaluate(generator_ip,
                    [np.ones(batch_size), energy_batch, ang_batch, ecal_batch]
                    , verbose=False, batch_size=batch_size))
        # Make loss dict 
        print('Total Test batches were {}'.format(index))
        discriminator_train_loss = np.mean(np.array(epoch_disc_loss), axis=0)
        discriminator_test_loss = np.mean(np.array(disc_test_loss), axis=0)
        generator_train_loss = np.mean(np.array(epoch_gen_loss), axis=0)
        generator_test_loss = np.mean(np.array(gen_test_loss), axis=0)
        train_history['generator'].append(generator_train_loss)
        train_history['discriminator'].append(discriminator_train_loss)
        test_history['generator'].append(generator_test_loss)
        test_history['discriminator'].append(discriminator_test_loss)
        # print losses
        print('{0:<20s} | {1:6s} | {2:12s} | {3:12s}| {4:5s} | {5:8s}'.format(
            'component', *discriminator.metrics_names))
        print('-' * 65)
        ROW_FMT = '{0:<20s} | {1:<4.2f} | {2:<10.2f} | {3:<10.2f}| {4:<10.2f} | {5:<10.2f}'
        print(ROW_FMT.format('generator (train)',
                             *train_history['generator'][-1]))
        print(ROW_FMT.format('generator (test)',
                             *test_history['generator'][-1]))
        print(ROW_FMT.format('discriminator (train)',
                             *train_history['discriminator'][-1]))
        print(ROW_FMT.format('discriminator (test)',
                             *test_history['discriminator'][-1]))

        # save weights every epoch                                                                                                                                                                                                                                                    
        generator.save_weights(WeightsDir + '/{0}{1:03d}.hdf5'.format(g_weights, epoch),
                               overwrite=True)
        discriminator.save_weights(WeightsDir + '/{0}{1:03d}.hdf5'.format(d_weights, epoch),
                                   overwrite=True)

        epoch_time = time.time()-test_start
        print("The Testing for {} epoch took {} seconds. Weights are saved in {}".format(epoch, epoch_time, WeightsDir))
        # save loss dict to pkl file
        pickle.dump({'train': train_history, 'test': test_history}, open(pklfile, 'wb'))
        
        # if a short analysis is to be performed for each epoch
        if analyse:
            print('analysing..........')
            atime = time.time()
            # load all test data
            for index, dtest in enumerate(Testfiles):
                if index == 0:
                   X_test, Y_test, ang_test, ecal_test = GetDataAngle(dtest, xscale=xscale, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
                else:
                   if X_test.shape[0] < nb_Test:
                     X_temp, Y_temp, ang_temp,  ecal_temp = GetDataAngle(dtest, xscale=xscale, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
                     X_test = np.concatenate((X_test, X_temp))
                     Y_test = np.concatenate((Y_test, Y_temp))
                     ang_test = np.concatenate((ang_test, ang_temp))
                     ecal_test = np.concatenate((ecal_test, ecal_temp))
            if X_test.shape[0] > nb_Test:
               X_test, Y_test, ang_test, ecal_test = X_test[:nb_Test], Y_test[:nb_Test], ang_test[:nb_Test], ecal_test[:nb_Test]
            else:
               nb_Test = X_test.shape[0] # the nb_test maybe different if total events are less than nEvents      
            var=gan.sortEnergy([np.squeeze(X_test), Y_test, ang_test], ecal_test, energies, ang=1)
            result = gan.OptAnalysisAngle(var, generator, energies, xpower = xpower, concat=2)
            print('{} seconds taken by analysis'.format(time.time()-atime))
            analysis_history['total'].append(result[0])
            analysis_history['energy'].append(result[1])
            analysis_history['moment'].append(result[2])
            analysis_history['angle'].append(result[3])
            print('Result = ', result)
            # write analysis history to a pickel file
            pickle.dump({'results': analysis_history}, open(resultfile, 'wb'))

if __name__ == '__main__':
    main()
