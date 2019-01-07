# Re: The organization of this module
# We balance two things:
# 1) using two sound servers with very different approaches to
# delivering sounds, and
# 2) having a similar API so other modules can query sound properties
# while still being agnostic to the sound server.
#
# So, We have base classes, but they can't encapsulate all the
# behavior for making sounds, so use an init_audio() method that
# creates sound conditional on the type of audio server.

# TODO: Be a whole lot more robust about handling different numbers of channels

import sys
from time import sleep
import json
from scipy.io import wavfile
from scipy.signal import resample
import numpy as np

from .. import prefs

# switch behavior based on audio server type
try:
    server_type = prefs.AUDIOSERVER
except:
    # TODO: The 'attribute don't exist' type - i think NameError?
    server_type = None

if server_type == "pyo":
    import pyo
elif server_type == "jack":
    import jackserver
else:
    # just importing to query parameters, not play sounds.
    pass

# later we will use either Pyo_Sound or Jack_Sound as a base object for inheritance
BASE_CLASS = None


class Pyo_Sound(object):
    # Metaclass for pyo sound objects
    PARAMS    = None # list of strings of parameters to be defined
    type      = None # string human readable name of sound
    duration  = None # duration in ms
    amplitude = None
    table     = None
    trigger   = None
    server_type = 'pyo'

    def __init__(self):
        pass

    def play(self):
        self.table.out()

    def table_wrap(self, audio, duration=None):
        '''
        Records a PyoAudio generator into a sound table, returns a tableread object which can play the audio with .out()
        '''

        if not duration:
            duration = self.duration

        # Duration is in ms, so divide by 1000
        # See https://groups.google.com/forum/#!topic/pyo-discuss/N-pan7wPF-o
        # TODO: Get chnls to be responsive to NCHANNELS in prefs. hardcoded for now
        tab = pyo.NewTable(length=(float(duration) / 1000),
                           chnls=prefs.NCHANNELS)  # Prefs should always be declared in the global namespace
        tabrec = pyo.TableRec(audio, table=tab, fadetime=0.005).play()
        sleep((float(duration) / 1000))
        self.table = pyo.TableRead(tab, freq=tab.getRate(), loop=0)

    def set_trigger(self, trig_fn):
        # Using table triggers, call trig_fn when table finishes playing
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)

class Jack_Sound(object):
    # base class for jack audio sounds
    PARAMS    = None # list of strings of parameters to be defined
    type      = None # string human readable name of sound
    duration  = None # duration in ms
    amplitude = None
    table     = None # numpy array of samples
    chunks    = None # table split into a list of chunks
    trigger   = None
    nsamples  = None
    fs        = jackserver.FS
    blocksize = jackserver.BLOCKSIZE
    server    = jackserver.SERVER
    server_type = 'jack'

    def __init__(self):
        pass

    def chunk(self):
        # break sound into chunks
        sound = self.table.astype(np.float32)
        sound_list = [sound[i:i+self.blocksize] for i in range(0, sound.shape[0], self.blocksize)]
        if sound_list[-1].shape[0] < self.blocksize:
            sound_list[-1] = np.pad(sound_list[-1],
                                    (0, self.blocksize-sound_list[-1].shape[0]),
                                    'constant')
        self.chunks = sound_list

    def set_trigger(self):
        # TODO: Implement sound-end triggers in jack sounds
        pass

    def get_nsamples(self):
        # given our fs and duration, how many samples do we need?
        self.nsamples = np.ceil((self.duration/1000.)*self.fs).as_type(np.int)


####################
if server_type == "pyo":
    BASE_CLASS = Pyo_Sound
elif server_type == "jack":
    BASE_CLASS = Jack_Sound
else:
    # just importing to query parameters, not play sounds.
    BASE_CLASS = object


class Tone(BASE_CLASS):
    '''
    The Humble Sine Wave
    '''
    PARAMS = ['frequency','duration','amplitude']
    type = 'Tone'

    def __init__(self, frequency, duration, amplitude=0.01, phase=0, **kwargs):
        super(Tone, self).__init__()

        self.frequency = float(frequency)
        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        if self.server_type == 'pyo':
            sin = pyo.Sine(self.frequency, mul=self.amplitude)
            self.table = self.table_wrap(sin)
        elif self.server_type == 'jack':
            self.get_nsamples()
            t = np.arange(self.nsamples)
            self.table = self.amplitude*np.sin(2*np.pi*self.frequency*t/self.fs)
            self.chunk()

class Noise(BASE_CLASS):
    '''
    White Noise straight up
    '''
    PARAMS = ['duration','amplitude']
    type='Noise'
    def __init__(self, duration, amplitude=0.01, **kwargs):
        super(Noise, self).__init__()

        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        if self.server_type == 'pyo':
            noiser = pyo.Noise(mul=self.amplitude)
            self.table = self.table_wrap(noiser)
        elif self.server_type == 'jack':
            self.get_nsamples()
            self.table = self.amplitude * np.random.rand(self.nsamples)
            self.chunk()

class File(BASE_CLASS):
    PARAMS = ['path', 'amplitude']
    type='File'

    def __init__(self, path, amplitude=0.01, **kwargs):
        super(File, self).__init__()

        self.path = path
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        fs, audio = wavfile.read(self.path)
        if audio.dtype in ['int16', 'int32']:
            audio = int_to_float(audio)

        # load file to sound table
        if self.server_type == 'pyo':
            self.dtable = pyo.DataTable(size=audio.shape[0], chnls=prefs.NCHANNELS, init=audio.tolist())

            # get server to determine sampling rate modification and duration
            server_fs = self.dtable.getServer().getSamplingRate()
            self.duration = float(self.dtable.getSize()) / float(fs)
            self.table = pyo.TableRead(table=self.dtable, freq=float(fs) / server_fs,
                                       loop=False, mul=self.amplitude)

        elif self.server_type == 'jack':
            self.duration = float(audio.shape[0]) / fs
            # resample to match our audio server's sampling rate
            if fs != self.fs:
                new_samples = self.duration*self.fs
                audio = resample(audio, new_samples)

            self.table = audio


class Speech(File):
    type='Speech'
    PARAMS = ['path', 'amplitude', 'speaker', 'consonant', 'vowel', 'token']
    def __init__(self, path, speaker, consonant, vowel, token, amplitude=0.05, **kwargs):
        super(Speech, self).__init__(path, amplitude, **kwargs)

        self.speaker = speaker
        self.consonant = consonant
        self.vowel = vowel
        self.token = token

        self.init_sound()







#######################
# Has to be at bottom so fnxns already defined when assigned.
SOUND_LIST = {
    'Tone':Tone,
    'Noise':Noise,
    'File':File,
    'Speech':Speech,
    'speech':Speech
}

STRING_PARAMS = ['path', 'speaker', 'consonant', 'vowel', 'type']


def int_to_float(audio):
    if audio.dtype == 'int16':
        audio = audio.astype(np.float16)
        audio = audio / (float(2 ** 16) / 2)
    elif audio.dtype == 'int32':
        audio = audio.astype(np.float16)
        audio = audio / (float(2 ** 32) / 2)

    return audio












