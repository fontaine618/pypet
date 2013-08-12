'''
Created on 17.05.2013

@author: Robert Meyer
'''

import logging
import petexceptions as pex
import tables as pt
import numpy as np
import scipy.sparse as spsp
import copy
from mypet.utils.helpful_functions import nest_dictionary
from mypet import globally
from pandas import DataFrame, Series

try:
    import cPickle as pickle
except:
    import pickle


class ObjectTable(DataFrame):
     def __init__(self, data=None, index = None, columns = None, copy=False):
        super(ObjectTable,self).__init__( data = data, index=index,columns=columns, dtype=object, copy=copy)




class BaseParameter(object):
    ''' Specifies the methods that need to be implemented for a Trajectory Parameter
    
    It is initialized with a location that specifies its position within the Trajectory, e.g.:
    Parameters.group.paramname
    The shorter name of the parameter is name=paramname, accordingly.
        
    For storing a parameter into hdf5 format the parameter implements a full node, how the storage 
    in the node is handled is left to the user.
        
    The parameter class can instantiate a single parameter as well as an array with several 
    parameters (of the same type) for exploration.
    
    Parameters can be locked to forbid further modification.
    If multiprocessing is desired the parameter must be pickable!
    ''' 
    def __init__(self, fullname):
        self._fullname = fullname
        split_name = fullname.split('.')
        self._name=split_name.pop()
        self._location='.'.join(split_name)
        self._comment = ''
        self._length = 0
        self._locked = False

    def _rename(self, fullname):
        self._fullname = fullname
        split_name = fullname.split('.')
        self._name=split_name.pop()
        self._location='.'.join(split_name)

    def get_comment(self):
        return self._comment

    def is_array(self):
        return len(self)>1


    def is_locked(self):
        return self._locked

    def get_location(self):
        return self._location
     
    def __len__(self):
        ''' Returns the length of the parameter.
        
        Only parameters that will be explored have a length larger than 1.
        If no values have been added to the parameter it's length is 0.
        '''
        return self._length

    
    def __store__(self):
        raise NotImplementedError( "Should have implemented this." )

    def __load__(self, load_dict):
        raise NotImplementedError( "Should have implemented this." )


    def to_str(self):
        ''' String representation of the value represented by the parameter. Note that representing
        the parameter as a string accesses it's value, but for simpler debugging, this does not
        lock the parameter!
        '''
        old_locked = self._locked
        try :
            return str(self.get())
        except Exception, e:
            return 'No Evaluation possible (yet)!'
        finally:
            self._locked = old_locked


    def __str__(self):
        return '%s: %s' % (self._fullname, self.to_str())

    def unlock(self):
        ''' Unlocks the locked parameter.'''
        self._locked = False

    def lock(self):
        self._locked = True


    def gfn(self):
        ''' Short for get_fullname '''
        return self.get_fullname()
    
    def get_fullname(self):
        ''' param.get_fullname() -> Returns the fullname of the parameter
        '''
        return self._fullname



    def set(self,data):
        ''' Sets specific values for a parameter.
        Has to raise ParameterLockedException if parameter is locked.

        For example:
        >>> param1.set(44.0)
        
        >>> print parm1.get()
        >>> 44.0
        '''
        raise NotImplementedError( "Should have implemented this." )



    def get(self,name):
        raise NotImplementedError( "Should have implemented this." )
    
    def explore(self, explorelist):
        ''' The default method to create and explored parameter containing an array of entries.
        For example:
        >>> param.explore([3.0,2.0,1.0])
        '''
        raise NotImplementedError( "Should have implemented this." )
    
    def set_parameter_access(self, n=0):
        ''' Prepares the parameter for further usage, and tells it which point in the parameter space should be
        accessed for future calls.
        :param n: The index of the parameter space point
        :return:
        '''
        raise NotImplementedError( "Should have implemented this." )
        
    def get_class_name(self):  
        return self.__class__.__name__

    def get_name(self):
        ''' Returns the name of the parameter.'''
        return self._name

    def is_empty(self):
        return len(self) == 0

    def shrink(self):
        ''' If a parameter is explored, i.e. it is an array, the whole exploration is deleted,
        and the parameter is no longer an array.
        :return:
        '''
        raise NotImplementedError( "Should have implemented this." )

    def empty(self):
        '''Erases all data in the parameter. If the parameter was an explored array it is also shrunk.
        '''
        raise NotImplementedError( "Should have implemented this." )
      
class Parameter(BaseParameter):
    ''' The standard parameter that handles creation and access to simulation parameters.
    
    Supported Data types are int, string, bool, float and numpy arrays.
    The actual data entries are stored in the _data list, each element is a Data item.
    
    If the parameter is not an array the list has only a single data element.
    Each parameter can have several entries (which are stored in a Data item) as entryname value pairs 
    of supported data.
    
    Entries can be accessed and created via natural naming:
    >>> param.entry1 = 3.8
    
    >>> print param.entry1
    >>> 3.8
    
    Note that the user cannot modify entries of parameter arrays except for the very first parameter.
    In fact, changing an entry of a parameter array deletes the array and reduces _data list to contain
    only a single parameter.
    To change the whole parameter array, the corresponding methods in the trajectory should be called,
    like explore, for instance.
    '''
   
    # # The comment that is added if no comment is specified
    # standard_comment = 'Dude, please explain a bit what your fancy parameter is good for!'

    def __init__(self, fullname, data=None, comment=None):
        super(Parameter,self).__init__(fullname)
        self._comment= comment
        self._data= None
        self._explored_data=tuple()#The Explored Data
        self._logger = logging.getLogger('mypet.parameter.Parameter=' + self._fullname)

        if not data == None:
            self.set(data)
        self._fullcopy = False


       
    def __getstate__(self):
        ''' Returns the actual state of the parameter for pickling. 
        '''
        result = self.__dict__.copy()


        # If we don't need a full copy of the Parameter (because a single process needs only access to a single point
        #  in the parameter space we can delete the rest
        if not self._fullcopy :
            result['_explored_data'] = tuple()

        del result['_logger'] #pickling does not work with loggers
        return result


    def __setstate__(self, statedict):
        ''' Sets the state for unpickling.
        '''
        self.__dict__.update( statedict)
        self._logger = logging.getLogger('mypet.parameter.Parameter=' + self._fullname)
      
        
    def set_parameter_access(self, n=0):
        if n >= len(self) and self.is_array():
            raise ValueError('You try to access the %dth parameter in the array of parameters, yet there are only %d potential parameters.' %(n,len(self)))
        else:
            self._data = self._explored_data[n]

    def _is_supported_data(self, data):
        ''' Checks if input data is supported by the parameter'''
        #result = isinstance(data, ( np.int, np.str, np.float, np.bool, np.complex))

        if isinstance(data, np.ndarray):
            dtype = data.dtype
            if np.issubdtype(dtype,np.str):
                dtype = np.str
        else:
            dtype=type(data)


        return dtype in globally.PARAMETER_SUPPORTED_DATA


    def _values_of_same_type(self,val1, val2):
        ''' Checks if two values are of the same type.
        
        This is important for exploration and adding of elements to the parameter array.
        New added elements must agree with the type of previous elements.
        '''
        
        if not type(val1) == type(val2):
            return False
        
        if type(val1) == np.array:
            if not val1.dtype == val2.dtype:
                return False
            
            if not np.shape(val1)==np.shape(val2):
                return False
        
        return True
        

    def add_comment(self,comment):
        ''' Adds a comment to the current comment. The comment is separated from the previous comment by a semicolon and
        a line break.
        
        :param comment: The comment as string which is added to the existing comment
        '''
        #Replace the standard comment:
        if self._comment == None:
            self._comment = comment
        else:
            self._comment = self._comment + ';\n ' + comment




    
    def set(self,data):
        ''' Adds data to the Parameter
        '''

        if self.is_locked():
            raise pex.ParameterLockedException('Parameter ' + self._name + ' is locked!')


        if self.is_array():
            raise AttributeError('Your Parameter is an explored array can no longer change values!')


        val = self._convert_data(data)

        if not self._is_supported_data(val):
            raise AttributeError('Unsupported data type: ' +str(type(val)))

        self._data= val
        self._length = 1




    def _convert_data(self, val):
        ''' Converts data, i.e. sets numpy arrays immutable.

        :param val: the val to convert
        :return: the numpy type val
        '''
        if isinstance(val, np.ndarray):
            val.flags.writeable = False
            return val

        return val


        
    def get_array(self):
        if not self._isarray():
            raise TypeError('Your parameter is not array, so cannot return the explored values')
        else:
            return self._explored_data[:]


    def explore(self, explore_list):
        ''' Changes a parameter to an array to allow exploration.
        
        *args and **kwargs are treated as in >>set(*arg,**kwargs)<< yet they need to contain
        lists of values of equal length that specify the exploration.
        '''
        if self.is_locked():
            raise pex.ParameterLockedException('Parameter %s is locked!' % self._fullname)

        if self.is_array():
            raise TypeError('Your Parameter %s is already explored, cannot explore it further!' % self._name)


        data_tuple = self._data_sanity_checks(explore_list)

        self._length = len(data_tuple)

        self._explored_data = data_tuple
        self.lock()

    def _data_sanity_checks(self, data_list):

        data_tuple = []

        default_val = self._data

        for val in data_list:
            newval = self._convert_data(val)


            if not self._is_supported_data(newval):
                raise TypeError('%s contains items of not supported type %s.' % (key,str(type(newval))))

            if not self._values_of_same_type(newval,default_val):
                raise TypeError('Data is not of the same type as the original entry value, new type is %s vs old type %s.' % ( str(type(newval)),str(type(default_val))))


            data_tuple.append(newval)

        return tuple(data_tuple)


    def __store__(self):
        store_dict={}
        store_dict['Data'] = ObjectTable(data={'data':[self._data]})
        if self.is_array():
            store_dict['ExploredData'] = ObjectTable(data={'data':self._explored_data})

        return store_dict


    def __load__(self,load_dict):
        self._data = load_dict['Data']['data'][0]
        if 'ExploredData' in load_dict:
            self._explored_data = tuple(load_dict['ExploredData']['data'].tolist())
            self._length = len(self._explored_data)
        else:
            self._length = 1


    def set_full_copy(self, val):
        assert isinstance(val, bool)
        self._fullcopy = val


    def get(self):
        self.lock() # As soon as someone accesses an entry the parameter gets locked
        return self._data


    def shrink(self):
        ''' Shrinks the parameter array to a single parameter.
        '''
        if self.is_empty():
            raise TypeError('Cannot shrink empty Parameter.')

        if self.is_locked():
            raise pex.ParameterLockedException('Parameter %s is locked!' % self._fullname)

        self._explored_data={}
        self._length = 1

    def empty(self):
        ''' Erases all data in the Parameter, if the parameter was explored, it is shrunk as well.
        '''
        if self.is_locked():
            raise pex.ParameterLockedException('Parameter %s is locked!' % self._fullname)

        self.shrink()
        self._data=None
        self._length = 0
    
     


class PickleParameter(Parameter):
    ''' A parameter class that supports all pickable objects, and simply writes the pickle dump into the table.
    '''

    identifier= '__pckl__'


    # def __init__(self, fullname, data, comment):
    #     if PickleParameter.identifier in fullname:
    #         raise ValueError('>>%s<< is in the name of the parameter >>%s<<. This is a reserved keyword, I cannot create the parameter.' %(PickleParameter.identifier,fullname))
    #

    def _is_supported_data(self, data):
        ''' There is no straightforward check if an object can be pickled, so you have to take care that it can be pickled '''
        return True


    def __store__(self):

        if not super(PickleParameter,self)._is_supported_data(self._data):
            store_dict={}
            dump = pickle.dumps(self._data)
            store_dict['Data'] = ObjectTable(data={'data'+PickleParameter.identifier:[dump]})
            if self.is_array():
                explore_list = list(self._explored_data)
                for idx, val in enumerate(explore_list):
                    dump = pickle.dumps(val)
                    explore_list[idx]=dump

                store_dict['ExploredData'] = ObjectTable(data={'data'+PickleParameter.identifier:explore_list})

            return store_dict
        else:
            return super(PickleParameter,self).__store__()


    def __load__(self,load_dict):
        data_table = load_dict['Data']
        data_name = data_table.columns.tolist()[0]
        if PickleParameter.identifier in data_name:
            dump = data_table['data'+PickleParameter.identifier][0]
            self._data = pickle.loads(dump)
            if 'ExploredData' in load_dict:
                explore_table = load_dict['ExploredData']

                pickle_col = explore_table['data'+PickleParameter.identifier]
                explore_list = []
                for idx,dump in enumerate(pickle_col):
                    explore_list.append(pickle.loads(dump))

                self._explored_data=tuple(explore_list)

                self._length = len(self._explored_data)
        else:
            super(PickleParameter,self).__load__(load_dict)





      

            
                            

class BaseResult(object):
    ''' The basic result class.
    
    It is a subnode of the tree, but how storage is handled is completely determined by the user.
    
    The result does know the name of the parent trajectory and the file because it might
    autonomously write results to the hdf5 file.
    '''
            
    def __init__(self, fullname):
        self._fullname = fullname
        split_name = fullname.split('.')
        self._name=split_name.pop()
        self._location='.'.join(split_name)

    def _rename(self, fullname):
        self._fullname = fullname
        split_name = fullname.split('.')
        self._name=split_name.pop()
        self._location='.'.join(split_name)

    def get_name(self):
        return self._name
    
    def get_fullname(self):
        return self._fullname

    def get_location(self):
        return self._location
    
    def gfn(self):
        return self.get_fullname()
    
    def get_class_name(self):  
        return self.__class__.__name__

    def __store__(self):
        raise NotImplementedError('Implement this!')

    def __load__(self, load_dict):
        raise  NotImplementedError('Implement this!')


    def is_empty(self):
        ''' Returns true if no data is stored into the result
        :return:
        '''
        raise NotImplementedError('You should implement this!')

    def empty(self):
        ''' Erases all data in the result and afterwards >>is_empty()<< should evaluate true
        :return:
        '''
        raise NotImplementedError('You should implement this!')



class SimpleResult(BaseResult):
    ''' Light Container that stores tables and arrays. Note that no sanity checks on individual data is made
    and you have to take care, that your data is understood by the Storage Service! It is assumed that
    results tend to be large and therefore sanity checks would be too expensive!
    '''

    def __init__(self, fullname, *args, **kwargs):
        super(SimpleResult,self).__init__(fullname)
        self._data = {}

        self._comment = kwargs.pop('comment',None)

        self.set(*args,**kwargs)



    def is_empty(self):
        return len(self._data)== 0

    def empty(self):
        self._data={}


    def set(self,*args, **kwargs):

        for idx,arg in enumerate(args):
            valstr = 'res'+str(idx)
            self.set_single(valstr,arg)

        for key, arg in kwargs.items():
            self.set_single(key,arg)

    def set_single(self, name, item):

        if name in ['comment', 'Comment']:
            assert isinstance(item,str)
            self._comment = item

        if name == 'Info':
            raise ValueError('>>Info<< is reserved for storing  information like name and location of the result etc.')

        if isinstance(item, (np.ndarray,ObjectTable,DataFrame)):
            self._data[name] = item
        else:
            raise TypeError('Your result >>%s<< of type >>%s<< is not supported.' % (name,str(type(item))))



    def __store__(self):
        store_dict ={}
        store_dict.update(self._data)
        return store_dict




    def __load__(self, load_dict):
        self._data = load_dict



    def __delattr__(self, item):
        if item[0]=='_':
            del self.__dict__[item]
        elif item in self._data:
            del self._data[item]
        else:
            raise AttributeError('Your result >>%s<< does not contain %s.' % (self.get_name(),item))

    def __setattr__(self, key, value):
        if key[0]=='_':
            self.__dict__[key] = value
        else:
            self.set_single(key, value)

    def __getattr__(self, name):

        if (not '_data' in self.__dict__ or
            not '_fullname' in self.__dict__):

            raise AttributeError('This is to avoid pickling issues!')

        if name in ['Comment', 'comment']:
            return self._comment

        if not name in self._data:
            raise  AttributeError('>>%s<< is not part of your result >>%s<<.' % (name,self._fullname))

        return self._data[name]

