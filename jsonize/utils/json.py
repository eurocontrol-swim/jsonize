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
from copy import deepcopy
from typing import Dict, Any, Union, List

from pyparsing import nums, Word, Optional, Literal, Group, ParseResults

__author__ = "EUROCONTROL (SWIM)"


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
            raise KeyError('The following path does not exist', path.split(at=key_pos + 1)[0])
        except TypeError:
            raise TypeError('The following item is not a dictionary: ', path.split(at=key_pos + 1)[0])
        except IndexError:
            raise IndexError(
                f'The item in the following path "{path.split(at=key_pos + 1)[0]}" cannot be accessed',
                path.split(at=key_pos + 1)[0]
            )
    return current_item


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
            json_copy = []
        elif len(in_path.json_path_structure) == 2 and isinstance(in_path.json_path_structure[1], int):
            json_copy = []
        else:
            json_copy = {}
    else:
        json_copy = deepcopy(json)
    parent_path, item_relative_path = in_path.split(-1)
    item_key = item_relative_path.json_path_structure[-1]

    # If the parent item doesnt exist we iteratively create a path of empty items until we get to
    # the parent
    try:
        parent_item = get_item_from_json_path(parent_path, json_copy)
    except (KeyError, TypeError, IndexError) as e:
        error_at_path = e.args[1]  # type: JSONPath
        item_key = error_at_path.json_path_structure[-1]

        if isinstance(item_key, int):
            json_copy = write_item_in_path([], error_at_path, json_copy)
        elif isinstance(item_key, str):
            json_copy = write_item_in_path({}, error_at_path, json_copy)
        elif isinstance(item_key, slice):
            raise ValueError('Writing on list slice is not supported.', in_path)

        return write_item_in_path(item, in_path, json_copy)

    if isinstance(parent_item, dict):
        if isinstance(item_key, str):
            parent_item.update({item_key: item})
        else:
            raise ValueError('Cannot write in a dictionary using integer key.')

    elif isinstance(parent_item, list):
        if isinstance(item_key, slice):
            raise ValueError('Writing on a list slice is not supported.')
        elif isinstance(item_key, str):
            parent_item.append({item_key: item})
        elif isinstance(item_key, int):
            if item_key >= 0:
                parent_item.insert(item_key, item)
            else:
                parent_item.insert(len(parent_item) + 2, item)
    else:
        raise TypeError('Cannot write item in path: ', parent_path)

    return json_copy
