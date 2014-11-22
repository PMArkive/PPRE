
import abc
import binascii
import json
from collections import namedtuple

from util.iter import auto_iterate


#: See Editable.restrict
Restriction = namedtuple('Restriction', 'name min_value max_value min_length'
                         ' max_length validator children')


class Editable(object):
    """Editable interface

    Attributes
    ----------
    keys : dict
        Mapping of restrictions

    Methods
    -------
    restrict
        Set restrictions on an attribute
    to_dict
        Generate a dict for this object
    to_json
        Generate a JSON string for this object
    """
    __metaclass__ = abc.ABCMeta

    @property
    def keys(self):
        """Map of restricted keys of this object. Keys are the names of the
        attributes. Values are Restriction instances.

        Returns
        -------
        keys : dict
        """
        try:
            return self._keys
        except AttributeError:
            self._keys = {}
            return self._keys

    def restrict(self, name, min_value=None, max_value=None, min_length=None,
                 max_length=None, validator=None, children=None):
        """Restrict an attribute. This adds the attribute to the key
        collection used to build textual representations.

        Parameters not passed will not be used to check validity.

        Parameters
        ----------
        name : string
            Name of the attribute
        min_value : optional
            Require value to be greater or equal to this value
        max_value : optional
            Require value to be less or equal to this value
        min_length : int, optional
            Require length of value to be greater or equal to this value
        max_length : int, optional
            Require length of value to be less or equal to this value
        validator : func(Editable, name, value), optional
            If set, this function gets passed the instance, name, and new
            value. This should raise a ValueError if the value should not
            be allowed.
        children : list of Restriction
            If not set, this will automatically grab the type of the
            currently set value
        """
        try:
            old_value = getattr(self, name)
        except AttributeError:
            raise ValueError('self.{name} is not set'.format(name=name))
        if children is None:
            # FIXME: This children thing might be stupid afterall
            children = []
            try:
                values = old_value.values()
            except:
                try:
                    values = list(old_value)
                except:
                    values = [old_value]
            used = []
            for value in values:
                if hasattr(value, 'restrict'):
                    cls = value.__class__
                    if cls in used:
                        continue
                    used.append(cls)
                    children.append(value)
        restriction = Restriction(name, min_value, max_value, min_length,
                                  max_length, validator, children)
        self.keys[name] = restriction

    def restrictInt8(self, name, **kwargs):
        params = {'min_value': -0x80, 'max_value': 0x7F}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictUInt8(self, name, **kwargs):
        params = {'min_value': 0, 'max_value': 0xFF}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictInt16(self, name, **kwargs):
        params = {'min_value': -0x8000, 'max_value': 0x7FFF}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictUInt16(self, name, **kwargs):
        params = {'min_value': 0, 'max_value': 0xFFFF}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictInt32(self, name, **kwargs):
        params = {'min_value': -0x80000000, 'max_value': 0x7FFFFFFF}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictUInt32(self, name, **kwargs):
        params = {'min_value': 0, 'max_value': 0xFFFFFFFF}
        params.update(kwargs)
        self.restrict(name, **params)

    def restrictUnused(self, name, **kwargs):

        def unused(editable, name, value):
            raise ValueError('"{name}" is unused'.format(name=name))
        params = {'validator': unused}
        params.update(kwargs)
        self.restrict(name, **params)

    def get_unrestricted(self, whitelist=None):
        """Get a list of all attributes that are not restricted

        This is a utility to verify all are restricted
        """
        keys = self.keys
        unrestricted = []
        if whitelist is None:
            whitelist = []
        for name, attr in self.__dict__.items():
            if hasattr(attr, '__call__'):
                continue
            if name in keys:
                continue
            if name[0] == '_':
                continue
            if name in whitelist:
                continue
            unrestricted.append(name)
        return unrestricted

    def __setattr__(self, name, value):
        try:
            restriction = self.keys[name]
            restriction.name
        except:
            pass
        else:
            if restriction.min_value is not None:
                if value < restriction.min_value:
                    raise ValueError(
                        '{name}: "{value}" is less than minimum "{restrict}"'
                        .format(name=name, value=value,
                                restrict=restriction.min_value))
            if restriction.max_value is not None:
                if value > restriction.max_value:
                    raise ValueError(
                        '{name}: "{value}" is more than maximum "{restrict}"'
                        .format(name=name, value=value,
                                restrict=restriction.max_value))
            if restriction.min_length is not None:
                if len(value) < restriction.min_length:
                    raise ValueError(
                        '{name}: "{value}" is less than length "{restrict}"'
                        .format(name=name, value=value,
                                restrict=restriction.min_length))
            if restriction.max_length is not None:
                if len(value) > restriction.max_length:
                    raise ValueError(
                        '{name}: "{value}" is more than length "{restrict}"'
                        .format(name=name, value=value,
                                restrict=restriction.max_length))
            if restriction.validator is not None:
                restriction.validator(self, name, value)
        super(Editable, self).__setattr__(name, value)

    def checksum(self):
        """Returns a recursive weak_hash for this instance"""
        weak_hash = 0
        for key in self.keys:
            try:
                name = self.keys[key].name
            except:
                name = key
            value = getattr(self, name)
            for sub_key, sub_value in auto_iterate(value)[2]:
                try:
                    sub_value = sub_value.checksum()
                except AttributeError as err:
                    pass
                weak_hash += hash(sub_value)
        return weak_hash

    def to_dict(self):
        """Generates a dict recursively out of this instance

        Returns
        -------
        out : dict
        """
        out = {}
        for key in self.keys:
            try:
                name = self.keys[key].name
            except:
                name = key
            value = getattr(self, name)
            container, adder, iterator = auto_iterate(value)
            for sub_key, sub_value in iterator:
                try:
                    sub_value = sub_value.to_dict()
                except AttributeError as err:
                    pass
                container = adder(container, sub_key, sub_value)
            out[key] = container
        return out

    def from_dict(self, source, merge=True):
        """Loads a dict into this instance

        Parameters
        ----------
        source : dict.
            Dict to load in
        merge : Bool
            If true, this merges with the current data. Otherwise it
            resets missing fields
        """
        for key in self.keys:
            try:
                value = source[key]
            except:
                # TODO: handle reset if merge=False
                continue
            old_value = getattr(self, key)
            try:
                old_value.from_dict(value, merge)
            except AttributeError:
                setattr(self, key, value)

    def to_json(self, **json_args):
        """Returns the JSON version of this instance

        Returns
        -------
        json_string : string
        """
        return json.dumps(self.to_dict(), **json_args)

    def print_restrictions(self, level=0):
        """Pretty-prints restrictions recursively"""
        prefix = '  '*level
        for key in self.keys:
            print('{prefix}{name}'.format(prefix=prefix, name=key))
            restriction = self.keys[key]
            try:
                restriction.name
            except:
                continue
            for restrict in ('min_value', 'max_value', 'min_length',
                             'max_length', 'validator'):
                value = getattr(restriction, restrict)
                if value is None:
                    continue
                if restrict == 'validator':
                    value = value.func_name
                print('{prefix}>> {restrict}="{value}"'.format(
                    prefix=prefix, restrict=restrict, value=value))
            for child in restriction.children:
                child.print_restrictions(level+1)

    def __repr__(self):
        return '<{cls}({value}) at {id}>'.format(cls=self.__class__.__name__,
                                                 value=self.to_dict(),
                                                 id=hex(id(self)))

    def _repr_pretty_(self, printer, cycle):
        if cycle:
            printer.text('{cls}(...)'.format(cls=self.__class__.__name__))
            return
        with printer.group(2, '{cls}('.format(cls=self.__class__.__name__),
                           ')'):
            printer.pretty(self.to_dict())