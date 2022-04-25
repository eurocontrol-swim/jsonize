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

import re
from enum import Enum
from typing import Tuple, Dict, Iterable, Union, List, Optional

from lxml.etree import ElementTree

from jsonize.utils.json import JSONPath

__author__ = "EUROCONTROL (SWIM)"


class XMLNodeType(Enum):
    VALUE = 'value'
    SEQUENCE = 'sequence'
    ATTRIBUTE = 'attribute'
    ELEMENT = 'element'


class XMLNode():
    """
    A class representing a XML node, defined by its XPath and an XMLNodeType.

    :param xpath: The XPath of the XML node.
    :param node_type: The XMLNodeType of the XML node.
    """
    def __init__(self, xpath: Union[str, XPath], node_type: XMLNodeType) -> None:
        self.path = XPath(str(xpath))
        self.node_type = node_type

    def __repr__(self):
        return f'XML {self.node_type.value} at {self.path}'

    def __eq__(self, other):
        return other and other.path == self.path and other.node_type == self.node_type

    def __hash__(self):
        return hash((self.path, self.node_type.VALUE))

    def relative_to(self, ancestor: XMLNode, in_place: bool = True) -> Optional[XMLNode]:
        """
        Makes the XMLNode's XPath relative to a given ancestor.

        :param ancestor: An XMLNode to which we want to make the current one relative to.
        :param in_place: If True the current instance will be updated (returns None). If False, a
                         new one will be created with the result of the relative path (returns an
                         XMLNode instance with the relative XPath).
        :return: None or a new instance of XMLNode with the relative path, as defined by the
                 in_place parameter.
        """
        if not in_place:
            return self.__class__(
                xpath=str(self.path.relative_to(ancestor=ancestor.path, in_place=False)),
                node_type=self.node_type
            )

        self.path.relative_to(ancestor=ancestor.path, in_place=in_place)

    def is_descendant_of(self, ancestor: XMLNode) -> bool:
        """
        Determines if the current XMLNode is a descendant of a given ancestor.

        :param ancestor: XMLNode of which we want to determine if the current one is a descendant.
        :return: True if the node is a descendant of ancestor, False otherwise.
        """
        return self.path.is_descendant_of(ancestor.path)

    def is_leaf(self, tree: Iterable[XMLNode]) -> bool:
        """
        Determines if the current XMLNode is a leaf with respect to an iterable of XMLNode defining
        the tree it belongs to.

        Determining if a particular node is a leaf can only be done in comparison with the entire
        XMl tree, hence in the tree parameter we must pass an iterable of all the XMLNodes of the
        XML. We consider a node a leaf if there are no elements in the tree that are descendant of
        the node.

        :param tree: An iterable of XMLNode containing each node of the XML tree.
        :return: True if the current node is not an ancestor of any of the XMLNode in the tree,
                 False otherwise.
        """
        if self.node_type == XMLNodeType.ATTRIBUTE:
            return True

        return all([not tree_node.is_descendant_of(self)
                    for tree_node in tree
                    if not tree_node.node_type == XMLNodeType.ATTRIBUTE])

    def to_jsonize(self,
                   values: str = 'value',
                   attributes: str = '',
                   with_namespaces: bool = True) -> Dict:
        """
        Infers a Jsonize mapping from the XMLNode. It does so by creating a direct translation of
        the XPath into JSONPath that can be fine-tuned via the 'values', 'attributes' and
        'namespaces' parameters. The JSON type is set to 'infer' which makes Jsonize attempt to
        find
        the best JSON type for the input data.

        :param values: Defines the name to be given in JSONPath to the value inside an XML element
                       node. An XML element can contain both attributes and a value. Aa natural
                       correspondence in JSON would be to map an element to an object as to be able
                       to contain all that data. This parameter specifies what should be the name
                       associated to the value of an XML element. It defaults to 'value'. If an
                       empty string is given then a JSON object will not be used, instead mapping
                       the value directly.

                       E.g. the following XPath 'element/subelement' will be transformed to the
                       following JSONPath:

                           'value': '$.element.subelement.value'
                           '': '$.element.subelement

                      If values is set to '', it could cause problems with elements that contain
                      attributes as there will not be a place to store them. Thus it's recommended
                      that this option is only used when the XML doesn't contain attributes.

        :param attributes: Defines the tag that will precede an XML attribute name in JSONPath. It
                           defaults to an empty string, resulting in no difference in the
                           representation of XML elements and attributes into JSON. Can be used to
                           define your own convention.

                          E.g. the following XPath '/element/subelement/@attribute will be
                          transformed to the following JSONPath:

                              '': $.element.subelement.attribute
                              '_': $.element.subelement._attribute
                              '@': $.element.subelement.@attribute

        :param with_namespaces: Defines how XML namespaces will be handled. It defaults to True,
                                resulting in shortened namespaces being kept in the JSONPath. A
                                False will drop them in the conversion to JSONPath and it should be
                                used with caution as it may result in name collisions.

                                E.g. the following XPath '/ns:element/nss:subelement will be
                                transformed as follows:

                                    'True': $.ns:element.nss:subelement
                                    'False': $.element.subelement

        :return: A dictionary containing the Jsonize mapping of the XMLNode.
        """
        json_path = str(self.path.to_json_path(attributes=attributes,
                                               with_namespaces=with_namespaces))

        if self.node_type == XMLNodeType.VALUE and values:
            json_path = f'{json_path}.{values}'

        return {
            'from': {
                'path': str(self.path),
                'type': self.node_type.value},
            'to': {
                'path': json_path,
                'type': 'infer'
            }
        }


class XMLSequenceNode(XMLNode):
    """
    Specialization of an XMLNode to a sequence of XML nodes.

    :param xpath: The XPath of the XML node.
    :param node_type: The XMLNodeType of the XML node.
    :param sub_nodes: An iterable of XML nodes that are contained in each item of the XML sequence.
    """
    def __init__(self,
                 xpath: Union[str, XPath],
                 sub_nodes: Iterable[XMLNode]) -> None:

        super().__init__(xpath=xpath, node_type=XMLNodeType.SEQUENCE)

        self.sub_nodes = [node.relative_to(self, in_place=False) for node in sub_nodes]

    def relative_to(self, ancestor: XMLNode, in_place: bool = True) -> Union[None, XMLNode]:
        """
        Makes the XMLNode's XPath relative to a given ancestor.

        :param ancestor: An XMLNode to which we want to make the current one relative to.

        :param in_place: If True the current instance will be updated (returns None). If False, a
                         new one will be created with the result of the relative path (returns an
                         XMLNode instance with the relative XPath).

        :return: None or a new instance of XMLNode with the relative path, as defined by the
                 in_place parameter.
        """
        if not in_place:
            return self.__class__(
                xpath=str(self.path.relative_to(ancestor=ancestor.path, in_place=False)),
                sub_nodes=self.sub_nodes
            )

        self.path.relative_to(ancestor=ancestor.path, in_place=in_place)

    def to_jsonize(self, values: str = 'value', attributes: str = '', with_namespaces: bool = True):
        """
        Infers a Jsonize mapping from the XMLSequenceNode. It does so by creating a direct
        translation of the XPath into JSONPath that can be fine-tuned via the 'attributes' and
        'namespaces' parameters. The JSON type is set to 'array' as it's the natural match of an
        XMLSequence.

        :param values: Defines the name to be given in JSONPath to the value inside an XML
                       element node. An XML element can contain both attributes and a value,
                       a natural correspondence in JSON would be to map an element to an object as
                       to be able to contain all that data. This parameter specifies what should be
                       the name associated to the value of an XML element. It defaults to 'value'.
                       If an empty string is given then a JSON object will not be used, instead
                       mapping the value directly.

                       E.g. the following XPath 'element/subelement' will be transformed to the
                       following JSONPath:
                           'value': '$.element.subelement.value'
                           '': '$.element.subelement

                      If values is set to '', it could cause problems with elements that contain
                      attributes as there will not be a place to store them. Thus it's recommended
                      that this option is only used when the XML doesn't contain attributes.

        :param attributes: Defines the tag that will precede an XML attribute name in JSONPath.
                           It defaults to an empty string, resulting in no difference in the
                           representation of XML elements and attributes into JSON. Can be used to
                           define your own convention.

                           E.g. the following XPath '/element/subelement/@attribute will be
                           transformed as follows:
                               '': $.element.subelement.attribute
                               '_': $.element.subelement._attribute
                               '@': $.element.subelement.@attribute

        :param with_namespaces: Defines how XML namespaces will be handled. It defaults to True,
                                resulting in shortened namespaces being kept in the JSONPath. A
                                False will drop them in the conversion to JSONPath and it should be
                                used with caution as it may result in name collisions.

                                E.g. the following XPath '/ns:element/nss:subelement will be
                                transformed as follows:

                                    'True': $.ns:element.nss:subelement
                                    'False': $.element.subelement

        :return: A dictionary containing the Jsonize mapping of the XMLNode.
        """
        jsonize = {
            'from': {
                'path': str(self.path),
                'type': self.node_type.value},
            'to': {
               'path': str(self.path.to_json_path(attributes=attributes,
                                                  with_namespaces=with_namespaces)),
               'type': 'array'
           }
       }

        if self.sub_nodes:
            jsonize['itemMappings'] = [sub_node.to_jsonize(values=values,
                                                           attributes=attributes,
                                                           with_namespaces=with_namespaces)
                                       for sub_node in self.sub_nodes]
        else:
            # If there are no sub_nodes then we create a single sub_node pointing to the value of
            # each XML element in the sequence.
            jsonize['itemMappings'] = [
                {
                   'from': {
                       'path': '.',
                       'type': 'value'
                   },
                   'to': {
                       'path': '@' + bool(values) * ('.' + values),
                       'type': 'infer'
                   }
                }
            ]

        return jsonize


class XPath():
    """
    Class representing an XPath.
    :param xpath: The string representation of the xpath.
    """

    def __init__(self, xpath: str):
        self.raw_xpath = xpath

    @property
    def _xpath_structure(self):
        return self.raw_xpath.split('/')

    def is_absolute(self) -> bool:
        """
        :return: Boolean indicating if the XPath is absolute.
        """
        return self.raw_xpath[0] == '/'

    def is_relative(self) -> bool:
        """
        :return: Boolean indicating if the XPath is relative.
        """
        return '.' in self._xpath_structure[0]

    def is_attribute(self) -> bool:
        """
        :return: Boolean indicating if the XPath refers to an attribute node.
        """
        return self._xpath_structure[-1][0] == '@'

    def is_descendant_of(self, ancestor: XPath) -> bool:
        """
        Determines if the current XPath is a descendant of a given ancestor.

        :param ancestor: XPath of a node of which we want to determine if the current one is a
                         descendant.
        :return: True if the node is a descendant of ancestor, False otherwise.
        """
        return f'{ancestor.raw_xpath}/' in self.raw_xpath and not self == ancestor

    def attribute_name(self) -> str:
        """
        :return: Name of the attribute node.
        :raises ValueError: If the XPath does not refer to an attribute node.
        """
        if not self.is_attribute():
            raise ValueError('The given xpath does not refer to an attribute.')

        return self._xpath_structure[-1][1:]

    def parent(self) -> XPath:
        """
        :return: An XPath representation of the parent element.
        """
        return XPath('/'.join(self._xpath_structure[:-1]))

    def split(self, at: int) -> Tuple[XPath, XPath]:
        """
        Splits an Xpath at the given index location.
        :param at: Index position where to split the XPath. Follows similar convention as python
        slice syntax. The at value is not included into the first XPath.
        :return: Tuple of XPath, the first one being the absolute path before the split at location
                 and the second one the relative XPath after the split location.
        """
        if at > 0:
            return (XPath('/'.join(self._xpath_structure[:at])),
                    XPath('/'.join(['.'] + self._xpath_structure[at:])))
        else:
            raise ValueError(f"at={at} parameter should be greater than 0.")

    def to_json_path(self, attributes: str = '', with_namespaces: bool = True) -> JSONPath:
        """
        Infers a JSONPath representation for the XPath.

        :param attributes: Defines the tag that will precede an XML attribute name in JSONPath.
                           It defaults to an empty string, resulting in no difference in the
                           representation of XML elements and attributes into JSON. Can be used to
                           define your own convention.

                           E.g. the following XPath '/element/subelement/@attribute will be
                           transformed as follows:
                               '': $.element.subelement.attribute
                               '_': $.element.subelement._attribute
                               '@': $.element.subelement.@attribute

        :param with_namespaces: Defines how XML namespaces will be handled. It defaults to True,
                                resulting in shortened namespaces being kept in the JSONPath. A
                                False will drop them in the conversion to JSONPath and it should be
                                used with caution as it may result in name collisions.

                                E.g. the following XPath '/ns:element/nss:subelement will be
                                transformed as follows:

                                    'True': $.ns:element.nss:subelement
                                    'False': $.element.subelement
        :return: A JSONPath representation of the XPath.
        """
        json_path = self.raw_xpath if with_namespaces else re.sub(r'[a-zA-Z]+:', '', self.raw_xpath)

        json_path = re.sub(r'/@', '/' + attributes, json_path)
        json_path = re.sub(r'^\./', '@/', json_path)
        json_path = re.sub(r'^/', '$/', json_path)
        json_path = re.sub(r'/', '.', json_path)
        json_path = JSONPath(json_path)
        json_path_structure = []
        for path_key in json_path.json_path_structure:
            if isinstance(path_key, int):
                if path_key <= 0:
                    raise ValueError(f"An XPath expression cannot contain an index <= 0, xpath= {self}")
                path_key += -1
            json_path_structure.append(path_key)
        return JSONPath.from_json_path_structure(json_path_structure)

    def relative_to(self, ancestor: XPath, in_place: bool = True) -> Union[None, XPath]:
        """
        Makes the XPath relative to a given ancestor.

        :param ancestor: An XPath to which we want to make the current one relative to.
        :param in_place: If True the current instance will be updated (returns None). If False, a
                         new one will be created with the result of the relative path (returns an
                         XPath instance with the relative XPath).
        :return: None or a new instance of XPath with the relative path, as defined by the in_place
                 parameter.
        """
        xpath = re.sub(r'^{}'.format(re.escape(str(ancestor))), '.', self.raw_xpath)

        if not in_place:
            return XPath(xpath)

        self.raw_xpath = xpath

    def shorten_namespaces(self,
                           xml_namespaces: Dict[str, str],
                           in_place: bool = True) -> Union[None, XPath]:

        def namespace_substitution(full_ns: str, xml_namespaces: Dict) -> str:
            short_ns = get_short_namespace(full_ns=full_ns, xml_namespaces=xml_namespaces)
            if short_ns is None:
                return ''
            else:
                return short_ns + ':'

        xpath = re.sub(r'\{([^\}]+)\}',
                       lambda x: namespace_substitution(x.group(1), xml_namespaces),
                       self.raw_xpath)

        if not in_place:
            return XPath(xpath)

        self.raw_xpath = xpath

        return self

    def remove_indices(self, in_place: bool = True) -> Union[None, XPath]:
        """
        Removes the XPath indices that are present in elements part of an XML sequence. i.e.
            '/element/subelement[2]/subsubelement[10]' becomes
            '/element/subelement/subsubelement'.

        :param in_place: If True the current instance will be updated (returns None). If False, a
                         new one will be created with the result of the relative path (returns an
                         XPath instance with the XPath without indices).
        :return: None or a new instance of XPath with the new XPath with indices removed, as
                 defined by the in_place parameter.
        """
        xpath = re.sub(r'\[[0-9]+\]', '', self.raw_xpath)

        if not in_place:
            return XPath(xpath)

        self.raw_xpath = xpath

    def _infer_node_type(self, infer_sequence: bool = False) -> XMLNodeType:
        """
        Attempts to infer the type of XML node from the XPath.

        A number of assumptions are needed for this inference to work. In particular:
            - Must be used on leaf nodes, XPath doesn't distinguish between the XML value inside and
              element and the element itself. In Jsonize we are interested in the values present at
              leaves, so whenever we identify an element we will assume it represents the value of
              a leaf.
            - Indices of sequences must have not been removed, as they will be used to determine
              that the element is part of a sequence.

        Because of these assumptions this method should be used with care, knowing what you are
        doing or under the supervision of an adult. It's made private, as to not be exposed in the
        public interface of the class. If needed, use judiciously.
        :param infer_sequence: Boolean indicating if elements part of a sequence will be inferred as SEQUENCE.
        :return: XMLNodeType that is inferred from the XPath.
        """
        if '@' in self._xpath_structure[-1]:
            node_type = XMLNodeType.ATTRIBUTE
        elif re.search(r'\[[0-9]+\]', self._xpath_structure[-1]) and infer_sequence:
            node_type = XMLNodeType.SEQUENCE
        else:
            node_type = XMLNodeType.VALUE
        return node_type

    def __str__(self) -> str:
        return self.raw_xpath

    def __repr__(self) -> str:
        return self.raw_xpath

    def __hash__(self):
        return hash(self.raw_xpath)

    def __eq__(self, other: XPath):
        return isinstance(other, XPath) and other.raw_xpath == self.raw_xpath


class XMLNodeTree():
    """
    A representation of an XML node tree, organized around sequences and leaves. The whole XML
    structure is expressed as XML leaf nodes. XML sequences, if any, serve as branch points in the
    tree. This mimics the Jsonize mapping structure and is used to infer the Jsonize mapping of a
    given XML.
    :param nodes: An iterable of XMLNode.
    """
    def __init__(self, nodes: Iterable[XMLNode] = None):
        self.nodes = nodes or []

    def to_jsonize(self, values: str = 'value', attributes: str = '', with_namespaces: bool = True):
        return [
            node.to_jsonize(values=values, attributes=attributes, with_namespaces=with_namespaces)
            for node in self.nodes
        ]


def get_short_namespace(full_ns: str, xml_namespaces: Dict[str, str]) -> str:
    """
    Inverse search of a short namespace by its full namespace value.

    :param full_ns: The full namespace of which the abbreviated namespace is to be found.
    :param xml_namespaces: A dictionary containing the mapping between short namespace (keys) and
                           long namespace (values).
    :return: If the full namespace is found in the dictionary, returns the short namespace.
    :raise KeyError: If the full namespace is not found in the dictionary.
    """
    for key, value in xml_namespaces.items():
        if full_ns == value:
            return key

    raise KeyError('The namespace is not found in "xml_namespaces".', full_ns)


def generate_node_xpaths(root: ElementTree,
                         xml_namespaces: Dict[str, str] = None) -> Iterable[XPath]:
    """
    Generator that yields all XPaths of an XML document.

    :param root: The ElementTree of the document.
    :param xml_namespaces: A dictionary containing the mapping of the namespaces.
    :return: A generator that yields all the possible XPaths.
    """
    all_elements = root.iterfind('//*')  # type: Iterable[ElementTree]

    for element in all_elements:
        element_path = root.getpath(element)
        attribs = (f'{element_path}/@{attrib_name}' for attrib_name, _ in element.attrib.items())

        yield XPath(element_path).shorten_namespaces(xml_namespaces, in_place=False)

        for attrib in attribs:
            yield XPath(attrib).shorten_namespaces(xml_namespaces, in_place=False)


def generate_nodes(tree: ElementTree, xml_namespaces: Dict[str, str] = None, clean_sequence_index: bool = False) -> Iterable[XMLNode]:
    """
    Generator that yields all possible XMLNode of an XML document.

    :param tree: The ElementTree of the XML document, containing its root Element.
    :param xml_namespaces: A dictionary containing the mapping of the namespaces.
    :param clean_sequence_index: A boolean indicating if indices in an XPath indicating elements of a sequence should be preserved.
    :return: A generator that yields all the possible XMLNode.
    """
    root = tree.getroot()
    root_xpath = XPath(tree.getpath(root))

    for xpath in generate_node_xpaths(tree, xml_namespaces):
        relative_xpath = xpath.relative_to(root_xpath, in_place=False)
        if clean_sequence_index:
            relative_xpath = relative_xpath.remove_indices(in_place=False)

        yield XMLNode(xpath=relative_xpath, node_type=xpath._infer_node_type())


def build_sequence_tree(
        sequence_nodes: List[XMLNode],
        leaf_nodes: List[Union[XMLNode, XMLSequenceNode]]) -> Tuple[List[XMLNode], List[XMLNode]]:

    if not sequence_nodes:
        return sequence_nodes, leaf_nodes

    trimmed_sequence_indices = []
    trimmed_leaf_indices = []
    deepest_sequences = []
    for i, node in enumerate(sequence_nodes):
        if node.is_leaf(sequence_nodes):
            sequence_node_leaves = []
            for ix, leaf in enumerate(leaf_nodes):
                if leaf.is_descendant_of(node):
                    sequence_node_leaves.append(leaf)
                    trimmed_leaf_indices.append(ix)
            trimmed_sequence_indices.append(i)
            sequence = XMLSequenceNode(xpath=node.path, sub_nodes=sequence_node_leaves)  # type: XMLSequenceNode
            deepest_sequences.append(sequence)

    trimmed_sequence_nodes = [node for i, node in enumerate(sequence_nodes)
                              if i not in trimmed_sequence_indices]
    trimmed_leaf_nodes = [node for i, node in enumerate(leaf_nodes) if i not in trimmed_leaf_indices]

    return build_sequence_tree(trimmed_sequence_nodes, trimmed_leaf_nodes + deepest_sequences)


def xml_node_from_xpath(xpath: XPath, root_xpath: XPath, clean_sequence_index: bool = False) -> XMLNode:
    relative_xpath = xpath.relative_to(root_xpath, in_place=False)
    if clean_sequence_index:
        relative_xpath = relative_xpath.remove_indices(in_place=False)

    return XMLNode(xpath=relative_xpath, node_type=xpath._infer_node_type())


def build_node_tree(tree: ElementTree, xml_namespaces: Dict[str, str] = None) -> XMLNodeTree:
    """
    Builds an XMLNodeTree from the XML ElementTree

    :param tree: The ElementTree of the XML document, containing its root Element.
    :param xml_namespaces: A dictionary containing the mapping of the namespaces.
    :return: The XMLNodeTree of the input ElementTree.
    """
    root_xpath = XPath(tree.getpath(tree.getroot()))
    all_nodes = set()
    sequence_node_xpaths = set()

    for node_xpath in generate_node_xpaths(tree, xml_namespaces):
        all_nodes.add(xml_node_from_xpath(node_xpath, root_xpath, clean_sequence_index=True))

        if node_xpath._infer_node_type(infer_sequence=True) == XMLNodeType.SEQUENCE:
            node_xpath.remove_indices(in_place=True)
            node_xpath.relative_to(root_xpath, in_place=True)
            sequence_node_xpaths.add(node_xpath)


    leaves = [
        node for node in all_nodes
        if node.is_leaf(all_nodes) and node.node_type != XMLNodeType.SEQUENCE
    ]

    sequences = [
        XMLNode(sequence_xpath, XMLNodeType.SEQUENCE) for sequence_xpath in sequence_node_xpaths
    ]

    return XMLNodeTree(nodes=build_sequence_tree(sequences, leaves)[1])


def find_namespaces(tree: ElementTree) -> Dict[str, str]:
    """
    Finds the namespaces defined in the ElementTree of an XML document. It looks for namespaces
    defined in the root element of the XML document. To avoid namespaces being left out, they shall
    all be defined in the root element of an XML document, instead of being defined across the
    document.

    :param tree: An lxml ElementTree containing the XML document from which to extract the namespaces.
    :return: A dictionary containing the mapping between short namespace and full namespace.
    """
    root = tree.getroot()
    namespaces = root.nsmap
    try:
        namespaces.pop(None)
    except KeyError:
        pass
    return namespaces
