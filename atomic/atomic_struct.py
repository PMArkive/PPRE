"""AtomicStruct version 2 Interface

AtomicStruct defines a structure for parsing raw data efficiently. The
substructures are compiled into a C-type equivalent.

"""
import ctypes

from util import BinaryIO


class AtomicError(RuntimeError):
    pass


class AtomicExhaustionError(AtomicError):
    pass


class AtomicContext(object):
    def __init__(self, atomic, key, value=True, rel=False):
        self.atomic = atomic
        self.key = key
        self.rel = rel
        self.value = value

    def __enter__(self):
        self.old_value = self.atomic.context[self.key]
        self.atomic.context[self.key] = self.value

    def __exit__(self, type_, value_, traceback):
        if self.rel and self.old_value > self.value:
            self.atomic.context[self.key] += self.old_value - self.value
        else:
            self.atomic.context[self.key] = self.old_value


class AtomicStruct(object):
    """Structure and data representation for a given inherited model.

    To use, subclass this. When initializing, call the field building
    functions (self.uint8('field_a'), etc.) and then freeze it with
    self.freeze().

    Once the model is frozen, this model has accessible data attributes
    that can be read or written.

    Use .load() to fill the data from a reader or .save() to build a
    writer.
    """
    alignment = 32  # : Bit alignment

    def __init__(self, name=None):
        self._fields = []
        self._anonymous = []
        self._type = None
        self._data = None
        self._defaults = {}
        self.context = {
            'field_pos': 0,
            'simulate': False
        }
        if name is None:
            self.name = self.__class__.__name__  # : Name of the type

    def _add(self, name, type_, **kwargs):
        """Adds a field to the structure

        Parameters
        ----------
        name : string
            Identifier. This name should be unique across the struct.
        type_ : _CData type
        width : int, optional
            Number of bits wide
        default : mixed
            Default to be filled in when data is cleared/initialized.

        Returns
        -------
        field : (str, type)

        Raises
        ------
        AtomicError
            If something cannot be added.
        """
        if not self.context['simulate']:
            if self._data is not None:
                raise AtomicError('Frozen Atoms cannot be modified')
            if name == '_':
                raise AtomicError('Subtype is not being simulated when '
                                  'fetched. base_obj={0}'.format(self))
            if 'width' in kwargs:
                field = (name, type_, kwargs['width'])
            else:
                field = (name, type_)
            self._fields.insert(self.context['field_pos'], field)
            self.context['field_pos'] += 1
            if 'default' in kwargs:
                self._defaults[name] = kwargs['default']
        return (name, type_)

    def simulate(self):
        """Provides a context that does not modify the current fields

        This is automatically used when pulling types out for arrays, et al.

        Returns
        -------
        AtomicContext : context

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> with atomic.simulate():
            field = atomic.uint8('b')
        >>> atomic.describe()
        struct Example_s {
          ubyte a;
        }
        >>> field
        ('b', ctypes.c_ubyte)
        """
        return AtomicContext(self, 'simulate')

    def _find(self, name):
        """Get the field position of a field by name

        Parameters
        ----------
        name : str
            Identifier to lookup

        Returns
        -------
        pos : int
            Index of field

        Raises
        ------
        IndexError
            If the field cannot be looked up by that name"""
        for idx, field in enumerate(self._fields):
            if field[0] == name:
                return idx
        raise IndexError('Could not find {0}'.format(name))

    def after(self, name=None):
        """Provides a context where modification happens directly after
        the specified field (by name)

        Parameters
        ----------
        name : str, optional
            Identifier to use as a reference. If not set, the context will
            refer to the start of the struct instead.

        Returns
        -------
        AtomicContext : context

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> atomic.uint8('b')
        >>> atomic.uint8('c')
        >>> with atomic.after('b'):
            atomic.uint8('d')
            atomic.uint8('e')
        >>> print(atomic.describe())
        struct Example_s {
          ubyte a;
          ubyte b;
          ubyte d;
          ubyte e;
          ubyte c;
        }
        >>>
        """
        if name is None:
            pos = 0
        else:
            pos = self._find(name)+1
        return AtomicContext(self, 'field_pos', pos, rel=True)

    def remove(self, name):
        """Removes a field by name

        Parameters
        ----------
        name : str
            Identifier to lookup and remove

        Returns
        -------
        field : (str, type)
            The removed field

        Raises
        ------
        IndexError
            If the field cannot be found
        AtomicError
            If this field could not be removed

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> atomic.uint8('b')
        >>> atomic.remove('a')
        >>> atomic.describe()
        struct Example_s {
          ubyte b;
        }
        """
        pos = self._find(name)
        if self.context['simulate']:
            return self._fields[pos]
        if self.context['field_pos'] >= pos:
            self.context['field_pos'] -= 1
        else:
            raise AtomicError('Cannot remove a field later than the '
                              'current position. target = {0}, current = {1}'
                              .format(pos, self.context['field_pos']))
        return self._fields.pop(pos)

    def replace(self, name):
        """Creates a context at a replaced field

        Parameters
        ----------
        name : str
            Identifier to lookup and replace

        Returns
        -------
        AtomicContext : context

        See Also
        ------
        AtomicStruct.remove

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> print(atomic.describe())
        struct Example_s {
          ubyte a;
        }
        >>> with atomic.replace('a'):
                atomic.uint16('a')
        >>> print(atomic.describe())
        struct Example_s {
          ushort a;
        }
        >>>
        """
        pos = self._find(name)
        ctx = AtomicContext(self, 'field_pos', pos, rel=True)
        with ctx:
            self.remove(name)
        return ctx

    def uint8(self, name, **kwargs):
        return self._add(name, ctypes.c_uint8, **kwargs)

    def int8(self, name, **kwargs):
        return self._add(name, ctypes.c_int8, **kwargs)

    def uint16(self, name, **kwargs):
        return self._add(name, ctypes.c_uint16, **kwargs)

    def int16(self, name, **kwargs):
        return self._add(name, ctypes.c_int16, **kwargs)

    def uint32(self, name, **kwargs):
        return self._add(name, ctypes.c_uint32, **kwargs)

    def int32(self, name, **kwargs):
        return self._add(name, ctypes.c_int32, **kwargs)

    def char(self, name, **kwargs):
        return self._add(name, ctypes.c_char, **kwargs)

    def string(self, name, length=1, **kwargs):
        return self.array(name, self.char, self, length=length)

    def get_type(self, type_callable, base_obj=None):
        """Gets the type of a type_callable owned by base_obj

        Parameters
        ----------
        type_callable : method
            Invoked method to generate the type. This expects a
            field (str, type) to be returned.
        base_obj : AtomicStruct, optional
            Owner of the method. This is used to ensure that type_callable is
            properly simulated. If not specified, the current instance will
            be used.

        Returns
        -------
        type : type
        """
        if base_obj is None:
            base_obj = self
        with base_obj.simulate():
            return type_callable('_')[1]

    def embed(self, name, type_callable, base_obj=None):
        """Embeds a type into the struct. The type's fields will be accessible
        without needing to reference `name`.

        Parameters
        ----------
        name : str
        type_callable : method
        base_obj : AtomicStruct, optional

        See Also
        --------
        AtomicStruct.get_type

        Returns
        -------
        field : (str, type)
        """
        self._anonymous.append(name)
        return self._add(name, self.get_type(type_callable, base_obj))

    def array(self, name, type_callable, base_obj=None, length=1):
        """Builds an `length`-long array of a type named `name`

        Parameters
        ----------
        name : str
        type_callable : method
        base_obj : AtomicStruct, optional
        length : int
            Fixed length of the array

        See Also
        --------
        AtomicStruct.get_type

        Returns
        -------
        field : (str, type)

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> atomic.uint8('b')
        >>> atomic.array('c', atomic.uint16, length=4):
        >>> atomic.describe()
        struct Example_s {
          ubyte a;
          ubyte b;
          ushort c[4];
        }
        """
        return self._add(name,
                         self.get_type(type_callable, base_obj) * length)

    def struct(self, name, type_callable, base_obj=None):
        """Adds a custom type field directly.

        Use AtomicStruct.base_struct as type_callable for an existing object.

        Parameters
        ----------
        name : str
        type_callable : method
        base_obj : AtomicStruct, optional

        See Also
        --------
        AtomicStruct.get_type

        Returns
        -------
        field : (str, type)

        Examples
        --------
        >>> atomic = AtomicStruct('Example')
        >>> atomic.uint8('a')
        >>> atomic.uint8('b')
        >>> other = AtomicStruct('Other')
        >>> other.uint8('a')
        >>> other.uint8('b')
        >>> other.freeze()
        >>> atomic.struct('c', atomic.base_struct)
        >>> atomic.describe()
        struct Example_s {
          ubyte a;
          ubyte b;
          struct Other_s {
            ubyte a;
            ubyte b;
          } c;
        }
        """
        return self._add(name, self.get_type(type_callable, base_obj))

    def base_struct(self, name):
        """Get a field that refers to this struct as its own type.

        `name` generally is not required, but it is used to match the
        existing interface.

        Returns
        -------
        field : (str, type)
        """
        return (name, self._type)

    def __len__(self):
        """Size of the data structure

        Returns
        -------
        size : int

        Raises
        ------
        TypeError
            If this model is not yet frozen.
        """
        return ctypes.sizeof(self._data)

    def freeze(self):
        """Lock the model's fields in place and compile the custom type.

        No modifications are able to be done after this. This is required
        before the compiled type and data become accessible.
        """
        self._type = type(self.name+'_s', (ctypes.Structure, ),
                          dict(_fields_=self._fields, _pack_=self.alignment,
                               _anonymous_=tuple(self._anonymous)))
        self._data = self._type()
        for key, value in self._defaults.iteritems():
            setattr(self._data, key, value)

    def describe(self):
        """Create a string representation of this struct.

        The result is compatible in C headers.

        Returns
        -------
        str
        """
        out = []

        data_type = type(ctypes.c_char)
        array_type = type(ctypes.c_char * 2)
        struct_type = type(ctypes.Structure)
        handle_struct = None

        def handle_field(field, level):
            field_type = type(field[1])
            if field_type is data_type:
                out.append('  '*level)
                out.append(str(field[1].__name__)[2:])
            elif field_type is struct_type:
                handle_struct(field[1], level)
            if field_type is array_type:
                handle_field((field[0], field[1]._type_), level)
                out.append('[{0}]'.format(field[1]._length_))
            else:
                out.append(' ')
                out.append(str(field[0]))

        def handle_struct(struct, level=0):
            out.append('  '*level)
            if not level:
                fields = struct._fields
                name = struct.name
            else:
                fields = struct._fields_
                name = struct.__name__
            out.append('struct {0}_s {{\n'.format(name))
            for field in fields:
                handle_field(field, level+1)
                out.append(';\n')
            out.append('  '*level)
            out.append('}')

        handle_struct(self)
        return ''.join(out)

    def load(self, reader):
        """Loads a reader into this model

        Parameters
        ----------
        reader : BinaryIO, string, file, other readable
        """
        reader = BinaryIO.reader(reader)
        amount = ctypes.sizeof(self._data)
        data = reader.read(amount)
        self._data = self._type.from_buffer_copy(data)

    def save(self, writer=None):
        """Creates a writer for this model

        Parameters
        ----------
        writer : BinaryIO, optional
            Destination to write into. If not specified, a new IO will be
            created.

        Returns
        -------
        writer : BinaryIO
            A new or modified writer that has this data in it
        """
        writer = writer if writer is not None else BinaryIO()
        amount = len(self)
        writer.write(ctypes.string_at(ctypes.addressof(self._data),
                                      size=amount))
        return writer