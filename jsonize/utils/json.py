"""
Copyright 2020 EUROCONTROL
==========================================

Redistribution and use in source and binary forms, with or without modification, are permitted
provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions
   and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of
conditions
   and the following disclaimer in the documentation and/or other materials provided with the
   distribution.
3. Neither the name of the copyright holder nor the names of its contributors may be used to
endorse
   or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
OF
THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

==========================================

Editorial note: this license is an instance of the BSD license template as provided by the Open
Source Initiative: http://opensource.org/licenses/BSD-3-Clause

Details on EUROCONTROL: http://www.eurocontrol.int
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Any, Union, List
import logging

from pyparsing import nums, Word, Optional, Literal, Group, ParseResults

__author__ = "EUROCONTROL (SWIM)"


logger = logging.getLogger(__name__)


class JSONPath():
    """
    Class representing a JSONPath using the dot notation.
    It supports absolute and relative paths, e.g.:
        '$.store.book.author' represents an absolute JSONPath
        '@.author.lastName' represent a relative JSONPath

    It does not support wildcards or parent operators.

    :param json_path: String representation of a JSONPath
    """

    def __init__(self, json_path: str) -> None:
        self.raw_json_path = json_path
        self.json_path_structure = JSONPath._json_path_structure(json_path)

    @classmethod
    def from_json_path_structure(cls, json_path_structure: List[Union[str, slice]]) -> JSONPath:
        return cls(cls.string_representation(json_path_structure))

    @staticmethod
    def _parse_slices(slice_substring: str) -> List[Union[int, slice]]:
        """
        Parses a string expression consisting of a number of bracket notation python slices
        (e.g. '[0], '[0:5:2]'...) and returns the list of index or slices to which it corresponds.

        :param slice_substring: A string consisting of 0 or more consecutive slice expressions using
                                bracket notation.
        :return: A list of slices parsed from the slice_substring.
        """

        slice_expression = Group(
            ("[" + Optional((Optional('-') + Word(nums))).setResultsName('start') +
                   Optional(Literal(':') + (Optional('-') + Word(nums)).setResultsName('stop') +
                   Optional(Literal(':') + (Optional('-') + Word(nums)).setResultsName('step'))) +
             "]"))

        multislice_expression = slice_expression[...]

        slice_matches = multislice_expression.parseString(slice_substring)  # type: List[ParseResults]
        slices = []
        for match in slice_matches:
            match_step = match.get('step')
            step = int(''.join(match_step)) if match_step else None

            match_stop = match.get('stop')
            stop = int(''.join(match_stop)) if match_stop else None

            match_start = match.get('start')
            if match_start:
                start = int(''.join(match_start))

                if not (stop or step):
                    # When only one parameter is given, we use index access instead of slice
                    slices.append(start)
                else:
                    slices.append(slice(start, stop, step))
            else:
                start = None
                slices.append(slice(start, stop, step))

        return slices

    @staticmethod
    def _json_path_structure(json_path_string: str) -> List[Union[str, int, slice]]:
        """
        Parses the raw input of a JSONPath into a structured list where each entry corresponds to a
        JSON node. Each entry of the list is either a string for node that are accessible by name
        (e.g. keys), an integer for index access to a list or a slice.

        :param json_path_string: JSONPath string representation.
        :return: A list
        """
        json_path_elements = json_path_string.split('.')
        json_path_structure = []

        for element in json_path_elements:
            try:
                slice_start = element.index('[')
                slice_substring = element[slice_start:]
                json_path_structure.append(element[:slice_start])
                json_path_structure += JSONPath._parse_slices(slice_substring)
            except ValueError:
                # If element.index() raises ValueError, no slice is defined in the element
                json_path_structure.append(element)

        return json_path_structure

    def is_absolute(self):
        """
        :return: Boolean indicating if the JSONPath is an absolute JSONPath.
        """
        return self.raw_json_path[0] == '$'

    def is_relative(self):
        """
        :return: Boolean indicating if the JSONPath is relative.
        """
        return self.raw_json_path[0] == '@'

    def split(self, at: int) -> (JSONPath, JSONPath):
        """
        Produces an absolute and a relative JSONPath by splitting the current one at the given index
        location. The at parameter behaves like the stop in a Python slice. That is:
            JSONPath('$.key1.key2.key3').split(2) results in:
            JSONPath('$.key1'), JSONPath('@.key2.key3')

        :param at: Index position where to split the XPath.
        :return: Tuple of XPath, the first one being the absolute path before the split at location
                 and the second one the relative XPath start at the split location.
        """
        if not abs(at) in range(1, len(self.json_path_structure) + 1):
            raise IndexError

        if len(self.json_path_structure) == 1:
            return JSONPath(self.json_path_structure[0]), JSONPath('@')

        return JSONPath.from_json_path_structure(self.json_path_structure[:at]), \
               JSONPath.from_json_path_structure(['@'] + self.json_path_structure[at:])

    def append(self, relative_path: JSONPath) -> None:
        """
        Appends a relative JSONPath to the end.

        :param relative_path: Relative JSONPath to append.
        :return: Result of appending the relative JSONPath to the end.
        """
        if not relative_path.is_relative():
            raise ValueError('Input "relative_path" is not a relative path.')

        self.raw_json_path = self.raw_json_path + relative_path.raw_json_path[1:]
        self.json_path_structure = self.json_path_structure + relative_path.json_path_structure[1:]

    @staticmethod
    def string_representation(json_path_structure: List[Union[str, int, slice]]):
        """
        Returns a string representation from a json_path_structure.

        :param json_path_structure: List of string, integer or slice that defines the JSONPath.
        """
        json_path = json_path_structure.pop(0)
        for element in json_path_structure:
            if isinstance(element, slice):
                start = element.start or ''
                stop = element.stop or ''
                step = element.step or ''

                json_path += f'[' + bool(start) * f'{start}' + ':' + bool(stop) * f'{stop}' + bool(step) * f':{step}' + ']'
            elif isinstance(element, int):
                json_path += f'[{element}]'
            else:
                json_path += '.' + element

        return json_path

    def __str__(self):
        return self.raw_json_path

    def __repr__(self):
        return self.raw_json_path

    def __eq__(self, other: JSONPath):
        return self.json_path_structure == other.json_path_structure


class JSONNodeType(Enum):
    """
    JSON base types.
    The value infer means, best match.
    """
    STRING = 'string'
    INTEGER = 'integer'
    NUMBER = 'number'
    OBJECT = 'object'
    ARRAY = 'array'
    BOOLEAN = 'boolean'
    NULL = 'null'
    INFER = 'infer'


class JSONNode():
    """
    Class representing a JSON node, defined by its JSONPath and its type
    :param json_path: The JSONPath of the node.
    :param node_type: A JSONNodeType enumeration specifying the type of the node.
    """

    def __init__(self, json_path: str, node_type: JSONNodeType):
        self.path = json_path
        self.node_type = node_type


def get_item_from_json_path(path: JSONPath, json: Union[Dict, List]) -> Any:
    """
    :param path: JSONPath of the item that is to be accessed.
    :param json: JSON serializable input from which to obtain the item.

    :raises KeyError: If the item at the given JSONPath does not exist.
    :raises TypeError: If an item along the JSONPath is not suscriptable.
    :return: Item at the given path from the input json.
    """
    current_item = json
    for key_pos, key in enumerate(path.json_path_structure):
        try:
            if key not in ['$', '@']:
                current_item = current_item[key]
        except KeyError:
            raise KeyError(f'The following path does not exist {path.split(at=key_pos + 1)[0]}', path.split(at=key_pos + 1)[0])
        except TypeError:
            raise TypeError(f'The following item is not a dictionary: {path.split(at=key_pos + 1)[0]}', path.split(at=key_pos + 1)[0])
        except IndexError:
            raise IndexError(
                f'The item in the following path "{path.split(at=key_pos + 1)[0]}" cannot be accessed',
                path.split(at=key_pos + 1)[0]
            )
    return current_item


def _write_item_in_array(item: Any, in_path: JSONPath, json: Union[Dict, List]) -> Union[Dict, List]:
    if isinstance(in_path.json_path_structure[-1], slice):
        raise ValueError('Writing on list slice is not supported.', in_path)
    if not isinstance(in_path.json_path_structure[-1], int):
        raise ValueError(f"Cannot write item into array, {in_path} doesn't point to an array entry.", in_path)
    array_path, relative_path = in_path.split(-1)
    array = get_item_from_json_path(array_path, json)
    if array is None:
        array = []
    array_length = len(array)
    if in_path.json_path_structure[-1] == -1:
        array.append(item)
    elif in_path.json_path_structure[-1] < -1 or in_path.json_path_structure[-1] > array_length:
        raise IndexError(f"Cannot write item into array, {in_path} index is out of bounds.")
    else:
        array.insert(in_path.json_path_structure[-1], item)
    return json


def _write_item_in_dict(item: Any, in_path: JSONPath, json: Union[Dict, List]) -> Union[Dict, List]:
    item_key = in_path.json_path_structure[-1]
    if not isinstance(item_key, str):
        raise ValueError(f"Cannot write item into dictionary, {in_path} doesn't point to a dictionary key.")
    parent_path, relative_path = in_path.split(-1)

    parent = get_item_from_json_path(parent_path, json)
    if item_key in parent.keys():
        logger.debug(f"Item at {in_path} already exists. Overwriting it.")
    parent.update({in_path.json_path_structure[-1]: item})
    return json

def _write_item_in_path(item: Any, in_path: JSONPath) -> Union[Dict, List]:
    for key in reversed(in_path.json_path_structure[1:]):
        if isinstance(key, str):
            item = {key: item}
        elif isinstance(key, int):
            item = [item]

    return item


def write_item_in_path(item: Any, in_path: JSONPath, json: Union[Dict, List, None]) -> Dict:
    """
    Attempts to write the given item at the JSONPath location. If an item already exists in the
    given JSONPath it will overwrite it.

    :param item: Item to write
    :param in_path: JSONPath specifying where to write the item.
    :param json: JSON serializable dictionary or list in which to write the item, if None given it
                 will try to infer the right data structure depending on the given JSONPath.
    :raises TypeError: If an item along the in_path is not an object and thus cannot contain child attributes.
    :return: A copy of the input json with the item written in the given JSONPath.
    """
    if json is None:
        if len(in_path.json_path_structure) == 1:
            return item
        elif isinstance(in_path.json_path_structure[1], int):
            json = []
        else:
            json = {}

    parent_path, item_relative_path = in_path.split(-1)
    item_key = item_relative_path.json_path_structure[-1]

    try:
        parent_item = get_item_from_json_path(parent_path, json)
        if isinstance(parent_item, dict):
            _write_item_in_dict(item, in_path, json)

        elif isinstance(parent_item, list):
            _write_item_in_array(item, in_path, json)
        else:
            raise TypeError('Cannot write item in path: ', parent_path)
        return json
    except (KeyError, TypeError, IndexError) as e:
        # If the parent item doesnt exist we iteratively create a path of empty items until we get to
        # the parent
        error_at_path: JSONPath = e.args[1]
        logger.debug(f"Path at {error_at_path} doesn't exist.")
        missing_path = in_path.split(at=len(error_at_path.json_path_structure))[1]
        logger.debug(f"Creating missing path: {missing_path}")

        missing_item = _write_item_in_path(item, missing_path)
        return write_item_in_path(missing_item, error_at_path, json)


def str_is_int(value: str) -> bool:
    """

    :param value:
    :return:
    """
    if not value or isinstance(value, bool):
        return False

    if value[0] in ['-', '+']:
        value = value[1:]

    return value.isdigit()


def str_is_float(value: str) -> bool:
    """

    :param value:
    :return:
    """
    if not value or isinstance(value, bool):
        return False

    if value[0] in ['-', '+']:
        value = value[1:]

    if value.lower() in ['nan', 'infinity', 'inf']:
        return False

    try:
        float(value)
    except ValueError:
        return False

    return True


def str_is_bool(value: str) -> bool:
    """

    :param value:
    :return:
    """
    return value.lower() in ['true', 'false']


def infer_json_type(value: Union[Dict, List, str, float, int, None, bool]) -> JSONNodeType:
    """
    Infers the most apt JSONNodeType of some input value.
    :param value: An value value for which we want to infer the JSONNodeType.
    :return: An enum value of JSONNodeType with the best fitting type.
    """
    if value is None:
        return JSONNodeType.NULL

    if isinstance(value, Dict):
        return JSONNodeType.OBJECT

    if isinstance(value, List):
        return JSONNodeType.ARRAY

    if isinstance(value, str):
        if str_is_bool(value):
            return JSONNodeType.BOOLEAN

        if str_is_float(value):
            return JSONNodeType.NUMBER

        if str_is_int(value):
            return JSONNodeType.INTEGER

        return JSONNodeType.STRING

    if isinstance(value, float):
        return JSONNodeType.INTEGER if value.is_integer() else JSONNodeType.NUMBER

    if isinstance(value, bool):
        return JSONNodeType.BOOLEAN

    raise ValueError('Unable to infer JSON type for {}'.format(value))
