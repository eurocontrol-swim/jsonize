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

from pathlib import Path
from json import load, dump, dumps
from typing import Dict, List, Optional, Callable, Iterable, Union, Iterator, Any
from abc import ABCMeta, abstractmethod
import re

from lxml.etree import parse as xml_parse
from lxml.etree import ElementTree, ETXPath

from jsonize.utils.xml import XMLNode, XMLNodeType, build_node_tree, generate_nodes, XPath
from jsonize.utils.json import (JSONNode,
                                JSONNodeType,
                                JSONPath,
                                write_item_in_path,
                                infer_json_type,
                                get_item_from_json_path)
import logging

__author__ = "EUROCONTROL (SWIM)"

logger = logging.getLogger(__name__)


class Transformation:
    """
    Class containing a named definition of a transformation that is applied onto the value of an XML
    Node before mapping it into a JSON Node.
    """

    def __init__(self, name: str, transformation: Callable):
        self.name = name
        self.transformation = transformation

    def __call__(self, input):
        return self.transformation(input)


class NodeMap(metaclass=ABCMeta):
    """
    Abstract class defining a mapping between two nodes.
    This abstract class is realized in XMLNodeToJSONNode class, mapping an XMLNode to a JSONNode and
    JSONNodeToJSONNode which maps a JSONNode to a JSONNode.
    """

    @abstractmethod
    def map(self, **kwargs):
        pass


class XMLNodeToJSONNode(NodeMap):
    """
    Class defining the mapping from an XMLNode to a JSONNode. A mapping is defined by providing the
    input XMLNode, the output JSONNode and an optional transform function that is to be applied to
    the input. When the input XMLNode is an XML sequence it accepts an item_mappings parameter that
    defines how each element of the sequence is to be mapped into an item in the JSON array.

    :param from_xml_node: The input XML Node, defined by an XPath and the type of XML node
                          ('element', 'attribute', 'sequence').
    :param to_json_node: The output JSON node to which the input is to be mapped, defined by a
                         JSONPath and its type ('string', 'integer', 'number', 'array', 'boolean').
    :param transform: An optional function that takes only one value as input and produces one value
                      as output, it is used to transform the input before writing it to the JSON
                      serializable dictionary. It can be used for string manipulation, unit
                      conversion, type casting, etc...
    :param item_mappings: An iterable of XMLNodeToJSONNode that defines how each item of a JSON
                          array is to be built from each element in an XML sequence.
    """

    def __init__(self,
                 from_xml_node: XMLNode,
                 to_json_node: JSONNode,
                 transform: Optional[Callable] = None,
                 item_mappings: Optional[Iterable[XMLNodeToJSONNode]] = None) -> None:
        self.from_xml_node = from_xml_node
        self.to_json_node = to_json_node
        self.transform = transform
        self.item_mappings = item_mappings or []

    def _get_attribute(self, xml_etree: ElementTree,
                       xml_namespaces: Dict = None) -> Optional[str]:
        attribute_path = self.from_xml_node.path
        parent_element_path = attribute_path.parent()
        attribute_name = attribute_path.attribute_name()

        if ':' in attribute_name:
            ns_separator_loc = attribute_name.find(':')
            short_ns = attribute_name[:ns_separator_loc]
            expanded_ns = xml_namespaces[short_ns]
            attribute_name = '{' + expanded_ns + '}' + attribute_name[ns_separator_loc + 1:]
        else:
            if xml_namespaces and xml_namespaces.get(None):
                expanded_ns = xml_namespaces[None]
                attribute_name = '{' + expanded_ns + '}' + attribute_name

        xpath = self.from_xml_node.path

        if xml_namespaces:
            if xml_namespaces.get(None):
                xml_namespaces['_'] = xml_namespaces.pop(None)
            if '_' in xml_namespaces.keys():
                xpath = xpath.replace_default_namespace('_', in_place=False)

        try:
            parent_element = xml_etree.xpath(str(xpath.parent()), namespaces=xml_namespaces)[0]
            input_value = parent_element.attrib[attribute_name]
        except (KeyError, AttributeError, IndexError):
            input_value = None
        return input_value

    def _get_element_value(self, xml_etree: ElementTree,
                           xml_namespaces: Dict = None,
                           strip_whitespace: bool = True) -> Optional[str]:
        xpath = self.from_xml_node.path

        if xml_namespaces:
            if xml_namespaces.get(None):
                xml_namespaces['_'] = xml_namespaces.pop(None)
            if '_' in xml_namespaces.keys():
                xpath = xpath.replace_default_namespace('_', in_place=False)

        try:
            xml_element = xml_etree.xpath(str(xpath), namespaces=xml_namespaces)[0]
            input_value = xml_element.text
            if strip_whitespace:
                input_value = input_value.strip()
        except (AttributeError, IndexError):
            input_value = None
        return input_value

    def _map_input(self, input: Optional[str], json: Union[Dict, List, None], ignore_empty: bool = True) -> Union[Dict, List]:
        logger.debug("Mapping {} into {}".format(self.from_xml_node.path, self.to_json_node.path))
        if ignore_empty:
            logger.debug("ignore_empty=True")
            if isinstance(input, str):
                input = re.sub(r"^\s*$", "", input)
            if input is None or input == '':
                logger.debug("input is empty. Ignoring...")
                return json

        if self.to_json_node.node_type == JSONNodeType.STRING:
            logger.debug("Mapping input to string")
            return write_item_in_path(input, JSONPath(self.to_json_node.path), json)

        if self.to_json_node.node_type == JSONNodeType.INTEGER:
            logger.debug("Mapping input to integer")
            try:
                casted_value = int(input)
                return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)
            except ValueError as e:
                raise ValueError(
                    f'The node at {self.from_xml_node.path} is not castable into int', e.args[0])

        if self.to_json_node.node_type == JSONNodeType.NUMBER:
            logger.debug("Mapping input to number")
            try:
                casted_value = float(input)
                return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)
            except ValueError as e:
                raise ValueError(
                    f'The node at {self.from_xml_node.path} is not castable into float', e.args[0])

        if self.to_json_node.node_type == JSONNodeType.BOOLEAN:
            logger.debug("Mapping input to boolean")
            if input == 'true':
                casted_value = True
            elif input == 'false':
                casted_value = False
            else:
                raise ValueError(f'The node at {self.from_xml_node.path} with value {input} '
                                 f'is not castable into a boolean. '
                                 f'Only "true" and "false" are valid XML boolean values.')

            return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)

        if self.to_json_node.node_type == JSONNodeType.NULL:
            logger.debug("Mapping input to null")
            return write_item_in_path(None, JSONPath(self.to_json_node.path), json)

        if self.to_json_node.node_type == JSONNodeType.INFER:
            try:
                inferred_json_type = infer_json_type(input)
            except ValueError:
                raise ValueError('Unable to infer JSON type for the value at {}'.format(self.from_xml_node.path))

            if inferred_json_type == JSONNodeType.BOOLEAN:
                if input == 'true':
                    casted_value = True
                elif input == 'false':
                    casted_value = False
                else:
                    casted_value = bool(input)
                return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.NUMBER:
                casted_value = float(input)
                return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.INTEGER:
                casted_value = int(input)
                return write_item_in_path(casted_value, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.STRING:
                return write_item_in_path(input, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.NULL:
                return write_item_in_path(None, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.ARRAY:
                return write_item_in_path(input, JSONPath(self.to_json_node.path), json)

            elif inferred_json_type == JSONNodeType.OBJECT:
                return write_item_in_path(input, JSONPath(self.to_json_node.path), json)
            else:
                raise ValueError("Input map for JSONNodeType of type {} not implemented".format(inferred_json_type))

    def map(self, xml_etree: ElementTree,
            json: Union[Dict, List, None],
            xml_namespaces: Dict = None,
            ignore_empty: bool = True) -> Dict:
        """
        Maps the XMLNode from xml_etree into the given json serializable dictionary.
        :param xml_etree: An XML ElementTree from which the input XMLNode is to be taken. If the
                          XMLNode is not found in the xml_etree it will be defaulted to None.
        :param json: The JSON serializable dictionary onto which the input is to be mapped.
        :param xml_namespaces: A dictionary defining the XML namespaces used in the xml_etree, if
                               they are used they must be provided to find the XMLNode via its XPath
                               expression.
        :param ignore_empty: A boolean indicating if a missing XML Node is to be mapped into the target JSON.
        :return: The JSON serializable dictionary with the input XMLNode mapped.
        """
        if self.from_xml_node.node_type == XMLNodeType.ATTRIBUTE:
            input = self._get_attribute(xml_etree, xml_namespaces)
        elif self.from_xml_node.node_type == XMLNodeType.VALUE:
            input = self._get_element_value(xml_etree, xml_namespaces)
        elif self.from_xml_node.node_type == XMLNodeType.SEQUENCE:
            if not self.item_mappings:
                raise ValueError(
                    "An item_mapping must be provided for an XML node of type 'sequence'.")
            input_sequence = xml_etree.findall(str(self.from_xml_node.path), xml_namespaces)
            if not input_sequence and ignore_empty:
                return json

            if self.to_json_node.node_type == JSONNodeType.ARRAY:
                items = []
                for element in input_sequence:
                    item = None
                    for mapping in self.item_mappings:
                        item = mapping.map(element, item, xml_namespaces, ignore_empty=ignore_empty)
                    items.append(item)
                return write_item_in_path(items, JSONPath(self.to_json_node.path), json)
            else:
                raise ValueError("Cannot map an XML sequence into {}".format(self.to_json_node.node_type))
        elif self.from_xml_node.node_type == XMLNodeType.ELEMENT:
            xml_element = xml_etree.find(str(self.from_xml_node.path), xml_namespaces)
            item = {}
            for mapping in self.item_mappings:
                item = mapping.map(xml_element, item, xml_namespaces, ignore_empty=ignore_empty)
            return write_item_in_path(item, JSONPath(self.to_json_node.path), json)
        else:
            raise ValueError(f"Not supported node type {self.from_xml_node.node_type.name}")
        if not input and ignore_empty:
            return json
        else:
            return self._map_input(input, json, ignore_empty)


class JSONNodeToJSONNode(NodeMap):
    def __init__(self,
                 from_json_node: JSONNode,
                 to_json_node: JSONNode,
                 transform: Optional[Callable] = None,
                 item_mappings: Optional[Iterable[JSONNodeToJSONNode]] = None) -> None:
        self.from_json_node = from_json_node
        self.to_json_node = to_json_node
        self.transform = transform
        self.item_mappings = item_mappings or []

    def _get_attribute(self, json: Union[Dict, List]) -> Optional[Any]:
        try:
            return get_item_from_json_path(JSONPath(self.from_json_node.path), json)
        except (KeyError, TypeError, IndexError) as e:
            logger.debug("Attribute at path {} doesn't exist".format(self.from_json_node.path))
            return None

    def map(self, input_json: Union[Dict, List],
            output_json: Union[Dict, List, None],
            ignore_empty: bool = True) -> Union[Dict, List]:
        input = self._get_attribute(input_json)
        if self.transform:
            input = self.transform(input)

        if not input:
            if ignore_empty:
                return output_json

        return write_item_in_path(input, in_path=JSONPath(self.to_json_node.path), json=output_json)


def _parse_from_json_node_map(node_map: Dict) -> JSONNode:
    return JSONNode(node_map['from']['path'], JSONNodeType(node_map['from']['type']))


def _parse_from_xml_node_map(node_map: Dict) -> XMLNode:
    return XMLNode(node_map['from']['path'], XMLNodeType(node_map['from']['type']))


def infer_path_type(path: str) -> Union[XPath, JSONPath]:
    """
    Infers the type of a path (XPath or JSONPath) based on its syntax.
    It performs some basic sanity checks to differentiate a JSONPath from an XPath.
    :param path: A valid XPath or JSONPath string.
    :return: An instance of JSONPath or XPath
    """
    if not path:
        raise ValueError("No path given")
    if path[0] in ['$', '@']:
        return JSONPath(path)
    else:
        if path[0] in ['.', '/']:
            return XPath(path)
        else:
            raise ValueError("Couldn't identify the path type for {}".format(path))


def parse_node_map(node_map: Dict, transformations: List[Transformation]) -> Union[XMLNodeToJSONNode, JSONNodeToJSONNode]:
    """
    Parses a serialized JSON (Python dictionary) defining a Jsonize node map and creates its
    corresponding XMLNodeToJSONNode mapping.

    :param node_map: A dictionary containing the serialized representation of a JSON NodeMap as
                     specified in Jsonize Schema.
    :param transformations: A list of Transformation from which the
    :return: An instance of XMLNodeToJSONNode or JSONNodeToJSONNode with the NodeMap definition.
    """
    from_path_type = infer_path_type(node_map['from']['path'])
    if isinstance(from_path_type, XPath):
        from_node = XMLNode(node_map['from']['path'], XMLNodeType(node_map['from']['type']))
    elif isinstance(from_path_type, JSONPath):
        from_node = JSONNode(node_map['from']['path'], JSONNodeType(node_map['from']['type']))
    to_node = JSONNode(node_map['to']['path'], JSONNodeType(node_map['to']['type']))

    try:
        unparsed_item_mappings = node_map['itemMappings']
        item_mappings = [parse_node_map(item_mapping, transformations)
                         for item_mapping in unparsed_item_mappings]  # type: [List[XMLNodeToJSONNode]]
    except KeyError:
        item_mappings = None
    try:
        transformation_name = node_map['transformation']  # type: Optional[str]
    except KeyError:
        transformation_name = ''

    if transformation_name:
        try:
            transformation = [transf for transf in transformations if transf.name == transformation_name][0]
        except IndexError:
            raise ValueError(f'The transformation with name "{transformation_name}" cannot '
                             f'be found in the "transformations" parameter.')
    else:
        transformation = None

    if isinstance(from_path_type, XPath):
        return XMLNodeToJSONNode(from_xml_node=from_node,
                                 to_json_node=to_node,
                                 item_mappings=item_mappings,
                                 transform=transformation)
    elif isinstance(from_path_type, JSONPath):
        return JSONNodeToJSONNode(from_json_node=from_node,
                                  to_json_node=to_node,
                                  item_mappings=item_mappings,
                                  transform=transformation)


def parse(jsonize_map: List[Dict], transformations: Optional[List[Transformation]] = None) \
        -> Union[List[XMLNodeToJSONNode], List[JSONNodeToJSONNode]]:
    """
    Produces a list of XMLNodeToJSONNode mappings from the Python serialization of a Jsonize map.
    A Jsonize map is defined as an instance of jsonize-map.schema.json.

    :param jsonize_map: A Python serialized Jsonize map, for example, the output of json.load
                        function when given the a Jsonize map defined in JSON.
    :param transformations: A list of Transformation that are used in the jsonize map.
    :return: A list of XMLNodeToJSONNode that defines the XML to JSON mapping.
    """
    return [parse_node_map(mapping, transformations or []) for mapping in jsonize_map]


def xml_document_to_dict(xml_document: Path,
                         jsonize_map_document: Optional[Path] = None,
                         jsonize_map: Optional[Iterable[XMLNodeToJSONNode]] = None,
                         xml_namespaces: Dict = None,
                         json: Optional[Dict] = None,
                         transformations: Optional[Iterable[Transformation]] = None,
                         ignore_empty: bool = True) -> Dict:
    """
    Transforms an XML document into a JSON serializable dictionary.

    :param xml_document: A Path to the XML document that is to be converted.
    :param jsonize_map_document: Path to a JSON file defining the Jsonize map.
    :param jsonize_map: An iterable of XMLNodeToJSONNode defining the Jsonize mapping.
                        If provided it overrides the parameter jsonize_map_document.
    :param xml_namespaces: A dictionary defining the XML namespaces with namespace shortname as keys
                           and the full namespace name as values. Follows the xml standard library
                           convention for XML namespaces.
    :param json: An input dictionary into which the XML document is to be mapped.
                 Defaults to an empty dictionary if none given.
    :param transformations: An iterable of Transformation that contains the functions that are invoked
                            in the Jsonize mapping.
    :param ignore_empty: A boolean indicating if missing XML Nodes should be ignored.
    :return: A (JSON serializable) Python dictionary containing the items defined in the mappings
            extracted from the xml_document.
    """
    transformations = transformations or []
    json = json or {}

    if not jsonize_map:
        try:
            assert jsonize_map_document is not None
        except AssertionError:
            raise ValueError('Jsonize map missing. Must be provided either via the parameter '
                             '"jsonize_map_document" or "jsonize_map".')

        with jsonize_map_document.open('r') as jsonize_map_file:
            jsonize_map: List[XMLNodeToJSONNode] = parse(load(jsonize_map_file), transformations)

    result = json
    xml_etree = xml_parse(str(xml_document))

    for mapping in jsonize_map:
        result = mapping.map(xml_etree, result, xml_namespaces=xml_namespaces, ignore_empty=ignore_empty)

    return result


def iter_map_xml_document_to_dict(xml_document: Path,
                                  xml_namespaces: Dict = None,
                                  json: Optional[Dict] = None,
                                  ignore_empty: bool = True) -> Iterator[Union[Dict, List]]:
    """
    Generator that iteratively maps each node encountered in the input xml_document.
    It will infer the output type for each node.
    :param xml_document: A Path to the XML document that is to be converted.
    :param xml_namespaces: A dictionary defining the XML namespaces with namespace shortname as keys
                           and the full namespace name as values. Follows the xml standard library
                           convention for XML namespaces.
    :param json: An input dictionary into which the XML document is to be mapped.
                 Defaults to an empty dictionary if none given.
    :param ignore_empty: A boolean indicating if missing XML Nodes should be ignored.
    :return: Yields a json serializable dictionary or list
    """
    json = json or {}
    xml_etree = xml_parse(str(xml_document))  # type: ElementTree
    root = xml_etree.getroot()
    root_xpath = XPath(xml_etree.getpath(root))
    all_elements = xml_etree.iterfind('//*')  # type: Iterable[ElementTree]

    for element in all_elements:
        ns_map = element.nsmap
        element_path = xml_etree.getpath(element)
        element_xpath = XPath(element_path)
        element_xpath.shorten_namespaces(ns_map, in_place=True).relative_to(root_xpath, in_place=True)
        attrib_paths = (XPath(f'{element_path}/@{attrib_name}') for attrib_name, _ in element.attrib.items())

        for attrib in attrib_paths:
            attrib.shorten_namespaces(ns_map, in_place=True)
            attrib.relative_to(root_xpath, in_place=True)
            yield attrib

    for node in generate_nodes(xml_etree, xml_namespaces):
        jsonize_mapping = node.to_jsonize(attributes='_')
        node_map: XMLNodeToJSONNode = parse_node_map(jsonize_mapping, transformations=[])
        node_map.map(xml_etree, json, xml_namespaces=xml_namespaces, ignore_empty=ignore_empty)
        yield json


def xml_document_to_json_document(xml_document: Path,
                                  json_document: Path,
                                  jsonize_map_document: Optional[Path] = None,
                                  jsonize_map: Optional[Iterable[XMLNodeToJSONNode]] = None,
                                  xml_namespaces: Dict = None,
                                  json: Optional[Dict] = None,
                                  transformations: Optional[Iterable[Transformation]] = None,
                                  ignore_empty: bool = True) -> None:
    """
    Transforms an XML document into a JSON document and saves it in the json_document Path.

    :param xml_document: A Path to the XML document that is to be converted.
    :param json_document: A Path defining where to save the JSON document that results from the mapping.
    :param jsonize_map_document: Path to a JSON file defining the Jsonize map.
    :param jsonize_map: An iterable of XMLNodeToJSONNode defining the Jsonize mapping.
                        If provided it overrides the parameter jsonize_map_document.
    :param xml_namespaces: A dictionary defining the XML namespaces with namespace shortname as keys
                           and the full namespace name as values. Follows the xml standard library
                           convention for XML namespaces.
    :param json: An input dictionary into which the XML document is to be mapped.
                 Defaults to an empty dictionary if none given.
    :param transformations: An iterable of Transformation that contains the functions that are invoked
                            in the Jsonize mapping.
    :param ignore_empty: A boolean indicating if missing XML Nodes should be ignored.
    :return: None, the function is pure side-effects.
    """
    result = xml_document_to_dict(xml_document=xml_document,
                                  jsonize_map_document=jsonize_map_document,
                                  jsonize_map=jsonize_map,
                                  xml_namespaces=xml_namespaces,
                                  json=json,
                                  transformations=transformations,
                                  ignore_empty=ignore_empty)

    with json_document.open('w') as result_file:
        result_file.write(dumps(result, indent=4))


def infer_jsonize_map(xml_document: Path,
                      output_map: Optional[Path] = None,
                      xml_namespaces: Optional[Dict[str, str]] = None,
                      value_tag: str = 'value',
                      attribute_tag: str = '',
                      with_namespaces: bool = True) -> List[Dict[str, Dict[str, str]]]:
    """
    This function will infer a Jsonize map for a given input xml_document. It does so by applying
    certain conventions of how to map XML nodes into JSON:
    - XML element sequences -> JSON array
    - XML attribute value -> JSON attribute
    - XML element value -> JSON attribute
    - Attempts to type cast the value of an XML attribute or element into the right JSON basetype
      using the Jsonize 'infer' JSONNodeType.

    It offers a few ways to fine-tune the Jsonize map to fit different conventions via the
    parameters:
    - value_tag: Specifies the key name of an XML element value. It defaults to the string 'value'.
    - attribute_tag: Specifies how to identify in the output JSON the keys coming from an XML
                     attribute. By default no particular differentiation is made but you can keep
                     track of which output keys come from attributes with this parameter.
                     E.g.: setting 'attribute_tag' to '@' will preprend the '@' symbol to all
                     attribute names.
    - keep_namespaces: XML element and attribute names are namespaced. This parameters controls if
                       these namespaces should be kept as part of the key names of the output JSON.
                       A True value will result in key names of the form 'ns:elementName' where ns
                       is the shortname of the namespace. This will prevent name collisions in the
                       output JSON as there is no notion of namespace in JSON. If name collisions
                       are not expected it may be set to False safely.

    Example:
    The following examples illustrate how the 3 parameters control the output

    - Parameters: value_tag='val', attribute_tag='_', keep_namespaces=True
    -- Input: <ns:element attrib="hi">42</ns:element>
    -- Output: {'ns:element': {'_attrib': 'hi', 'val': 42}}

    - Parameters: value_tag='value', attribute_tag='', keep_namespaces=False
    -- Input: <ns:element attrib="hi">42</ns:element>
    -- Output: {'element': {'attrib': 'hi', 'value': 42}}

    :param xml_document: A Path to the XML document which we want to create a Jsonize map.
    :param output_map: A Path to where the JSON file with Jsonize map is to be stored.
    :param xml_namespaces: Dictionary containing the definition of the namespaces used in the XML document.
    :param value_tag: Specifies the key name of XML element values, it defaults to the string
    'value'
    :param attribute_tag: Specifies a string to prepend in the key name of XML attribute values,
    it defaults to the
                          empty string.
    :param with_namespaces: Specifies if XML namespaces should be kept in the JSON output,
    it defaults to True.
    :return: the jsonize map
    """
    xml_etree = xml_parse(str(xml_document))
    node_tree = build_node_tree(xml_etree, xml_namespaces=xml_namespaces)

    jsonized = node_tree.to_jsonize(values=value_tag,
                                    attributes=attribute_tag,
                                    with_namespaces=with_namespaces)

    if output_map:
        with output_map.open('w') as output_file:
            dump(jsonized, output_file)

    return jsonized


def json_document_to_dict(input_document: Path,
                          jsonize_map_document: Optional[Path] = None,
                          jsonize_map: Optional[Iterable[JSONNodeToJSONNode]] = None,
                          json: Union[Dict, List] = None,
                          transformations: Optional[Iterable[Transformation]] = None,
                          ignore_empty: bool = True) -> Dict:
    """
    Applies a Jsonize map to a JSON document, returns a JSON serializable dictionary.
    :param input_document: A Path to the input JSON document that is to be converted.
    :param jsonize_map_document: Path to a JSON file defining the Jsonize map.
    :param jsonize_map: An iterable of JSONNodeToJSONNode defining the Jsonize mapping.
                        If provided it overrides the parameter jsonize_map_document.
    :param json: An input dictionary into which the XML document is to be mapped.
                 Defaults to an empty dictionary if none given.
    :param transformations: An iterable of Transformation that contains the functions that are invoked
                            in the Jsonize mapping.
    :param ignore_empty: A boolean indicating if missing values should be ignored.
    :return: A (JSON serializable) Python dictionary containing the items defined in the mappings
    extracted from the input_document.
    """
    transformations = transformations or []
    json = json or {}

    if not jsonize_map:
        try:
            assert jsonize_map_document is not None
        except AssertionError:
            raise ValueError('Jsonize map missing. Must be provided either via the parameter '
                             '"jsonize_map_document" or "jsonize_map".')

        with jsonize_map_document.open('r') as jsonize_map_file:
            jsonize_map: List[JSONNodeToJSONNode] = parse(load(jsonize_map_file), transformations)

    result = json
    with input_document.open('r', encoding='utf-8') as input_file:
        input_dict = load(input_file)

    for mapping in jsonize_map:
        result = mapping.map(input_dict, result, ignore_empty=ignore_empty)

    return result


def json_document_to_json_document(input_document: Path,
                                   output_document: Path,
                                   jsonize_map_document: Optional[Path] = None,
                                   jsonize_map: Optional[Iterable[JSONNodeToJSONNode]] = None,
                                   json: Union[Dict, List] = None,
                                   transformations: Optional[Iterable[Transformation]] = None,
                                   ignore_empty: bool = True) -> None:
    """
    Transforms a JSON document into another JSON document based on the given Jsonize mapping
    and saves it in the output_document Path.

    :param input_document: A Path to the input JSON document that is to be converted.
    :param output_document: A Path defining where to save the JSON document that results from the mapping.
    :param jsonize_map_document: Path to a JSON file defining the Jsonize map.
    :param jsonize_map: An iterable of JSONNodeToJSONNode defining the Jsonize mapping.
                        If provided it overrides the parameter jsonize_map_document.
    :param json: An input dictionary into which the XML document is to be mapped.
                 Defaults to an empty dictionary if none given.
    :param transformations: An iterable of Transformation that contains the functions that are invoked
                            in the Jsonize mapping.
    :param ignore_empty: A boolean indicating if missing values should be ignored.
    :return: None, the function is pure side-effects.
    """
    result = json_document_to_dict(input_document=input_document,
                                   jsonize_map_document=jsonize_map_document, jsonize_map=jsonize_map,
                                   json=json, transformations=transformations, ignore_empty=ignore_empty)

    with output_document.open('w') as result_file:
        result_file.write(dumps(result, indent=4))