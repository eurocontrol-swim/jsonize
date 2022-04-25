import unittest
from jsonize.utils.xml import XPath, XMLNode, XMLNodeType, XMLSequenceNode, XMLNodeTree, \
    get_short_namespace, find_namespaces, generate_node_xpaths
from jsonize.utils.json import JSONPath
from pathlib import Path
from lxml import etree


class TestNamespaceSubstitution(unittest.TestCase):
    namespaces = {None: 'http://defaultNamespace.com/default/ns/3.0',
                  'gml': 'http://www.opengis.net/gml/3.2',
                  'adrmsg': 'http://www.eurocontrol.int/cfmu/b2b/ADRMessage',
                  'aixm': 'http://www.aixm.aero/schema/5.1',
                  'xlink': 'http://www.w3.org/1999/xlink'}

    def test_namespace_found(self):
        full_ns = 'http://www.opengis.net/gml/3.2'
        short_ns = 'gml'
        self.assertEqual(short_ns, get_short_namespace(full_ns, self.namespaces))

    def test_namespace_not_found(self):
        with self.assertRaises(KeyError):
            get_short_namespace('http://notfound.com', self.namespaces)

    def test_namespace_substitution(self):
        xpath = XPath(
            '/{http://www.eurocontrol.int/cfmu/b2b/ADRMessage}ADRMessage/{http://www.eurocontrol.int/cfmu/b2b/ADRMessage}hasMember[1]/{http://defaultNamespace.com/default/ns/3.0}Route/@{http://www.opengis.net/gml/3.2}id')
        short_xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember[1]/Route/@gml:id')
        with self.subTest():
            self.assertEqual(short_xpath, xpath.shorten_namespaces(self.namespaces, in_place=False))
        with self.subTest():
            xpath.shorten_namespaces(self.namespaces, in_place=True)
            self.assertEqual(short_xpath, xpath)


class TestXPathManipulations(unittest.TestCase):

    def test_index_removal(self):
        xpath = XPath('/root/element[10]/subelement/subsubelement[1]/@attribute')
        reference = XPath('/root/element/subelement/subsubelement/@attribute')
        with self.subTest():
            self.assertEqual(xpath.remove_indices(in_place=False), reference)
        with self.subTest():
            xpath.remove_indices(in_place=True)
            self.assertEqual(xpath, reference)

    def test_make_relative_path(self):
        with self.subTest():
            xpath = XPath('/root/element[10]/subelement/subsubelement[1]/@attribute')
            parent = XPath('/root/element[10]')
            reference = XPath('./subelement/subsubelement[1]/@attribute')
            with self.subTest():
                self.assertEqual(xpath.relative_to(parent, in_place=False), reference)
            with self.subTest():
                xpath.relative_to(parent, in_place=True)
                self.assertEqual(xpath, reference)

        with self.subTest():
            xpath = XPath('/root/element[10]/subelement/subsubelement[1]')
            parent = xpath
            reference = XPath('.')
            with self.subTest():
                self.assertEqual(xpath.relative_to(parent, in_place=False), reference)
            with self.subTest():
                xpath.relative_to(parent, in_place=True)
                self.assertEqual(xpath, reference)


class TestInferJsonPath(unittest.TestCase):

    def test_absolute_path(self):
        xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
        reference = JSONPath('$.adrmsg:ADRMessage.adrmsg:hasMember.aixm:Route.@gml:id')
        self.assertEqual(reference, xpath.to_json_path(attributes='@', with_namespaces=True))

    def test_relative_path(self):
        xpath = XPath('./adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
        reference = JSONPath('@.adrmsg:ADRMessage.adrmsg:hasMember.aixm:Route.@gml:id')
        self.assertEqual(reference, xpath.to_json_path(attributes='@', with_namespaces=True))

    def test_ignore_namespaces(self):
        xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
        reference = JSONPath('$.ADRMessage.hasMember.Route.@id')
        self.assertEqual(reference, xpath.to_json_path(attributes='@', with_namespaces=False))

    def test_change_attribute_tag(self):
        with self.subTest():
            xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
            reference = JSONPath('$.ADRMessage.hasMember.Route._id')
            self.assertEqual(reference, xpath.to_json_path(attributes='_', with_namespaces=False))

        with self.subTest():
            xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
            reference = JSONPath('$.ADRMessage.hasMember.Route.id')
            self.assertEqual(reference, xpath.to_json_path(attributes='', with_namespaces=False))

        with self.subTest():
            xpath = XPath('/adrmsg:ADRMessage/adrmsg:hasMember/aixm:Route/@gml:id')
            reference = JSONPath('$.adrmsg:ADRMessage.adrmsg:hasMember.aixm:Route.attrib_gml:id')
            self.assertEqual(reference, xpath.to_json_path(attributes='attrib_', with_namespaces=True))

    def test_sequence_path(self):
        with self.subTest():
            xpath = XPath("/adrmsg:ADRMessage/adrmsg:hasMember[1]/aixm:Route/@gml:id")
            reference = JSONPath("$.adrmsg:ADRMessage.adrmsg:hasMember[0].aixm:Route._gml:id")
            self.assertEqual(reference, xpath.to_json_path(attributes="_", with_namespaces=True))

        with self.subTest():
            xpath = XPath("/adrmsg:ADRMessage/adrmsg:hasMember[1]/aixm:Route/@gml:id")
            reference = JSONPath("$.ADRMessage.hasMember[0].Route.id")
            self.assertEqual(reference, xpath.to_json_path(attributes="", with_namespaces=False))

        with self.subTest():
            xpath = XPath("/adrmsg:ADRMessage/adrmsg:hasMember[-1]/aixm:Route/@gml:id")
            reference = JSONPath("$.ADRMessage.hasMember[-1].Route.id")
            self.assertRaises(ValueError)


class TestXPathRelations(unittest.TestCase):

    def test_descendance(self):
        with self.subTest():
            ancestor = XPath('/root/element')
            descendant = XPath('/root/element/subelement/leaf/@attribute')
            self.assertTrue(descendant.is_descendant_of(ancestor))

        with self.subTest():
            ancestor = XPath('/root/element')
            not_descendant = XPath('/root/otherElement/subelement/leaf')
            self.assertFalse(not_descendant.is_descendant_of(ancestor))

        with self.subTest():
            ancestor = XPath('/root/element')
            not_descendant = XPath('/root/elemental')
            self.assertFalse(not_descendant.is_descendant_of(ancestor))

    def test_is_leaf(self):
        all_nodes = [XMLNode('/root/element/@attrib', XMLNodeType.ATTRIBUTE),
                     XMLNode('/root/element/subelement/subsubelement', XMLNodeType.ELEMENT),
                     XMLNode('/root/anotherElement', XMLNodeType.ELEMENT),
                     XMLNode('/root/element', XMLNodeType.ELEMENT)]
        with self.subTest():
            self.assertTrue(XMLNode('/root/element/@attrib', XMLNodeType.ATTRIBUTE).is_leaf(all_nodes))
        with self.subTest():
            self.assertTrue(XMLNode('/root/element/subelement/subsubelement', XMLNodeType.ELEMENT).is_leaf(all_nodes))
        with self.subTest():
            self.assertTrue(XMLNode('/root/anotherElement', XMLNodeType.ELEMENT).is_leaf(all_nodes))
        with self.subTest():
            self.assertFalse(XMLNode('/root/element', XMLNodeType.ELEMENT).is_leaf(all_nodes))

    def test_is_attribute(self):
        attribute_node = XPath('/root/element/@attribute')
        ns_attribute_node = XPath('/ns:root/nss:element/@nss:attribute')
        element_node = XPath('root/element')
        with self.subTest():
            self.assertTrue(attribute_node.is_attribute())
        with self.subTest():
            self.assertTrue(ns_attribute_node.is_attribute())
        with self.subTest():
            self.assertFalse(element_node.is_attribute())

    def test_is_absolute(self):
        absolute_xpath = XPath('/root/element/subelement')
        relative_xpath = XPath('./element/@attribute')
        with self.subTest():
            self.assertTrue(absolute_xpath.is_absolute())
        with self.subTest():
            self.assertFalse(relative_xpath.is_absolute())

    def test_is_relative(self):
        absolute_xpath = XPath('/root/element/subelement')
        relative_xpath = XPath('./element/@attribute')
        with self.subTest():
            self.assertFalse(absolute_xpath.is_relative())
        with self.subTest():
            self.assertTrue(relative_xpath.is_relative())

    def test_attribute_name(self):
        attribute_xpath = XPath('./element/@attri')
        absolute_attribute_xpath = XPath('/ns:root/nss:element/@nss:attribute')
        element_xpath = XPath('/root/element/subelement')
        with self.subTest():
            self.assertEqual(attribute_xpath.attribute_name(), 'attri')
        with self.subTest():
            self.assertEqual(absolute_attribute_xpath.attribute_name(), 'nss:attribute')
        with self.subTest():
            with self.assertRaises(ValueError):
                element_xpath.attribute_name()

    def test_parent(self):
        absolute_attribute_xpath = XPath('/ns:root/nss:element/@nss:attribute')
        relative_element_xpath = XPath('./element/subelement')
        with self.subTest():
            self.assertEqual(absolute_attribute_xpath.parent(), XPath('/ns:root/nss:element'))
        with self.subTest():
            self.assertEqual(relative_element_xpath.parent(), XPath('./element'))

    def test_split(self):
        absolute_attribute_xpath = XPath('/ns:root/nss:element/@nss:attribute')
        relative_element_xpath = XPath('./element/subelement')
        with self.subTest():
            # TODO: Evaluate if the numbering convention is appropriate
            self.assertEqual(absolute_attribute_xpath.split(1), (XPath(''), XPath('./ns:root/nss:element/@nss:attribute')))
            self.assertEqual(absolute_attribute_xpath.split(2), (XPath('/ns:root'), XPath('./nss:element/@nss:attribute')))
        with self.subTest():
            self.assertEqual(relative_element_xpath.split(1), (XPath('.'), XPath('./element/subelement')))
            self.assertEqual(relative_element_xpath.split(2), (XPath('./element'), XPath('./subelement')))
        with self.subTest():
            with self.assertRaises(ValueError):
                relative_element_xpath.split(-1)


class TestJsonizeMapGeneration(unittest.TestCase):
    xml_attribute_node = XMLNode('/ns:root/nss:element/@nss:attrib', XMLNodeType.ATTRIBUTE)
    xml_value_node = XMLNode('/ns:root/nss:element/nss:subelement/ns:subsubelement', XMLNodeType.VALUE)
    xml_sequence_node = XMLSequenceNode('/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                        [XMLNode('./child', XMLNodeType.VALUE),
                                         XMLNode('./@nss:attrib', XMLNodeType.ATTRIBUTE)])
    xml_empty_sequence_node = XMLSequenceNode('/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                              [])
    xml_tree = XMLNodeTree([xml_attribute_node,
                            xml_value_node,
                            xml_sequence_node])

    def test_xml_attribute_jsonize(self):
        with self.subTest():
            self.assertEqual(self.xml_attribute_node.to_jsonize(attributes='@', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/@nss:attrib',
                                       'type': 'attribute'},
                              'to': {'path': '$.ns:root.nss:element.@nss:attrib',
                                     'type': 'infer'}})
        with self.subTest():
            self.assertEqual(self.xml_attribute_node.to_jsonize(attributes='', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/@nss:attrib',
                                       'type': 'attribute'},
                              'to': {'path': '$.ns:root.nss:element.nss:attrib',
                                     'type': 'infer'}})
        with self.subTest():
            self.assertEqual(self.xml_attribute_node.to_jsonize(attributes='', with_namespaces=False),
                             {'from': {'path': '/ns:root/nss:element/@nss:attrib',
                                       'type': 'attribute'},
                              'to': {'path': '$.root.element.attrib',
                                     'type': 'infer'}})

    def test_xml_value_jsonize(self):
        with self.subTest():
            self.assertEqual(self.xml_value_node.to_jsonize(attributes='@', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                       'type': 'value'},
                              'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement.value',
                                     'type': 'infer'}})
        with self.subTest():
            self.assertEqual(self.xml_value_node.to_jsonize(values='', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                       'type': 'value'},
                              'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement',
                                     'type': 'infer'}})

    def test_xml_sequence_jsonize(self):
        with self.subTest():
            self.assertEqual(self.xml_sequence_node.to_jsonize(values='', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                       'type': 'sequence'},
                              'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement',
                                     'type': 'array'},
                              'itemMappings': [
                                  {'from': {'path': './child',
                                            'type': 'value'},
                                   'to': {'path': '@.child',
                                          'type': 'infer'}
                                   },
                                  {'from': {'path': './@nss:attrib',
                                            'type': 'attribute'},
                                   'to': {'path': '@.nss:attrib',
                                          'type': 'infer'}
                                   }
                              ]
                              }
                             )

        with self.subTest():
            self.assertEqual(self.xml_empty_sequence_node.to_jsonize(values='', with_namespaces=True),
                             {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                       'type': 'sequence'},
                              'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement',
                                     'type': 'array'},
                              'itemMappings': [
                                  {'from': {'path': '.',
                                            'type': 'value'},
                                   'to': {'path': '@',
                                          'type': 'infer'}
                                   }
                              ]
                              })

        with self.subTest():
            self.assertEqual(self.xml_empty_sequence_node.to_jsonize(values='value', attributes='_', with_namespaces=False),
                             {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                       'type': 'sequence'},
                              'to': {'path': '$.root.element.subelement.subsubelement',
                                     'type': 'array'},
                              'itemMappings': [
                                  {'from': {'path': '.',
                                            'type': 'value'},
                                   'to': {'path': '@.value',
                                          'type': 'infer'}
                                   }
                              ]
                              })

    def test_xml_tree_jsonize(self):
        with self.subTest():
            self.assertEqual(self.xml_tree.to_jsonize('value', attributes='@', with_namespaces=True),
                             [
                                 {'from': {'path': '/ns:root/nss:element/@nss:attrib',
                                           'type': 'attribute'},
                                  'to': {'path': '$.ns:root.nss:element.@nss:attrib',
                                         'type': 'infer'}
                                  },
                                 {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                           'type': 'value'},
                                  'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement.value',
                                         'type': 'infer'}
                                  },
                                 {'from': {'path': '/ns:root/nss:element/nss:subelement/ns:subsubelement',
                                           'type': 'sequence'},
                                  'to': {'path': '$.ns:root.nss:element.nss:subelement.ns:subsubelement',
                                         'type': 'array'},
                                  'itemMappings': [
                                      {'from': {'path': './child',
                                                'type': 'value'},
                                       'to': {'path': '@.child.value',
                                              'type': 'infer'}
                                       },
                                      {'from': {'path': './@nss:attrib',
                                                'type': 'attribute'},
                                       'to': {'path': '@.@nss:attrib',
                                              'type': 'infer'}
                                       }
                                  ]
                                  }
                             ]
                             )


class TestXMLNodeManipulations(unittest.TestCase):
    xml_node = XMLNode('/root/element', XMLNodeType.ELEMENT)
    deep_xml_sequence = XMLSequenceNode('/root/element/subelement/sequence',
                                        sub_nodes=[XMLNode('./@attribute', XMLNodeType.ATTRIBUTE),
                                                   XMLNode('./value', XMLNodeType.VALUE)])
    deep_attribute = XMLNode('/root/element/subelement/@attrib', XMLNodeType.ATTRIBUTE)

    def test_sequence_relative_to(self):
        with self.subTest():
            self.assertEqual(self.deep_xml_sequence.relative_to(self.xml_node, in_place=False),
                             XMLSequenceNode('./subelement/sequence',
                                             sub_nodes=[XMLNode('./@attribute', XMLNodeType.ATTRIBUTE),
                                                        XMLNode('./value', XMLNodeType.VALUE)])
                             )
        with self.subTest():
            self.deep_xml_sequence.relative_to(self.xml_node, in_place=True)
            self.assertEqual(self.deep_xml_sequence,
                             XMLSequenceNode('./subelement/sequence',
                                             sub_nodes=[XMLNode('./@attribute', XMLNodeType.ATTRIBUTE),
                                                        XMLNode('./value', XMLNodeType.VALUE)])
                             )

    def test_node_relative_to(self):
        with self.subTest():
            self.assertEqual(self.deep_attribute.relative_to(self.xml_node, in_place=False),
                             XMLNode('./subelement/@attrib', XMLNodeType.ATTRIBUTE)
                             )

        with self.subTest():
            self.deep_attribute.relative_to(self.xml_node, in_place=True)
            self.assertEqual(self.deep_attribute,
                             XMLNode('./subelement/@attrib', XMLNodeType.ATTRIBUTE)
                             )


sample_no_namespace = """<?xml version="1.0"?>
<catalog>
   <book id="bk101">
      <author>Gambardella, Matthew</author>
      <title>XML Developer's Guide</title>
      <genre>Computer</genre>
      <price>44.95</price>
      <publish_date>2000-10-01</publish_date>
      <description>An in-depth look at creating applications
      with XML.</description>
   </book>
   <book id="bk102">
      <author>Ralls, Kim</author>
      <title>Midnight Rain</title>
      <genre>Fantasy</genre>
      <price>5.95</price>
      <publish_date>2000-12-16</publish_date>
      <description>A former architect battles corporate zombies,
      an evil sorceress, and her own childhood to become queen
      of the world.</description>
   </book>
</catalog>
"""

sample_namespaced = """<?xml version="1.0"?>
<message:AIXMBasicMessage xmlns:message="http://www.aixm.aero/schema/5.1.1/message"
	xmlns:gts="http://www.isotc211.org/2005/gts" xmlns:gco="http://www.isotc211.org/2005/gco"
	xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="http://www.opengis.net/gml/3.2"
	xmlns:gss="http://www.isotc211.org/2005/gss" xmlns:aixm="http://www.aixm.aero/schema/5.1.1"
	xmlns:gsr="http://www.isotc211.org/2005/gsr" xmlns:gmd="http://www.isotc211.org/2005/gmd"
	xmlns:xlink="http://www.w3.org/1999/xlink"
	xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
	xsi:schemaLocation="http://www.aixm.aero/schema/5.1.1/message http://www.aixm.aero/schema/5.1.1/message/AIXM_BasicMessage.xsd"	gml:id="M0000001">
	<gml:boundedBy>
		<gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">
			<gml:lowerCorner>-32.0886111111111 -47.0</gml:lowerCorner>
			<gml:upperCorner>57.690815969999996 52.4283333333333</gml:upperCorner>
		</gml:Envelope>
	</gml:boundedBy>
</message:AIXMBasicMessage>
"""

sample_with_default_namespace = """<?xml version="1.0"?>
<IATA_AIDX_FlightLegNotifRQ xmlns="http://www.iata.org/IATA/2007/00" xmlns:ba="http://baplc.com/extensionSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" AltLangID="en-us" PrimaryLangID="en-us" Target="Test" Version="15.1" TimeStamp="2015-06-03T14:47:03.612Z" TransactionIdentifier="FLT:NFAM" SequenceNmbr="2084">
	<Originator CompanyShortName="BA"/>
	<DeliveringSystem CompanyShortName="BA"/>
	<FlightLeg>
		<LegIdentifier>
			<Airline CodeContext="3">BA</Airline>
			<FlightNumber>8277</FlightNumber>
			<DepartureAirport CodeContext="3">AAL</DepartureAirport>
			<ArrivalAirport CodeContext="3">OSL</ArrivalAirport>
			<OriginDate>2015-06-03</OriginDate>
			<RepeatNumber>1</RepeatNumber>
		</LegIdentifier>
		<LegData>
			<OperationalStatus RepeatIndex="1" CodeContext="9750">OFB</OperationalStatus>
			<OperationalStatus RepeatIndex="2" CodeContext="9750">OFB</OperationalStatus>
			<ServiceType>J</ServiceType>
			<OwnerAirline>
				<Airline>BA</Airline>
			</OwnerAirline>
			<AircraftInfo>
				<AircraftType>FRJ</AircraftType>
				<Registration>OYNCP</Registration>
			</AircraftInfo>
		</LegData>
		<TPA_Extension>
			<ba:FlightCrewAirline CodeContext="3">BA</ba:FlightCrewAirline>
			<ba:CabinCrewAirline CodeContext="3">BA</ba:CabinCrewAirline>
		</TPA_Extension>
	</FlightLeg>
</IATA_AIDX_FlightLegNotifRQ>
"""


class TestFindNamespaces(unittest.TestCase):

    def test_exist_namespaces(self):
        root = etree.fromstring(sample_namespaced)
        xml_tree = etree.ElementTree(root)
        xml_namespaces = {'message': 'http://www.aixm.aero/schema/5.1.1/message', 'gts': 'http://www.isotc211.org/2005/gts',
                          'gco': 'http://www.isotc211.org/2005/gco', 'xsd': 'http://www.w3.org/2001/XMLSchema',
                          'gml': 'http://www.opengis.net/gml/3.2', 'gss': 'http://www.isotc211.org/2005/gss',
                          'aixm': 'http://www.aixm.aero/schema/5.1.1', 'gsr': 'http://www.isotc211.org/2005/gsr',
                          'gmd': 'http://www.isotc211.org/2005/gmd', 'xlink': 'http://www.w3.org/1999/xlink',
                          'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        self.assertEqual(find_namespaces(xml_tree), xml_namespaces)

    def test_no_namespaces(self):
        root = etree.fromstring(sample_no_namespace)
        xml_tree = etree.ElementTree(root)
        xml_namespaces = {}
        self.assertEqual(find_namespaces(xml_tree), xml_namespaces)

    def test_default_namespace(self):
        root = etree.fromstring(sample_with_default_namespace)
        xml_tree = etree.ElementTree(root)
        xml_namespaces = {None: 'http://www.iata.org/IATA/2007/00',
                          'ba': 'http://baplc.com/extensionSchema',
                          'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        self.assertEqual(find_namespaces(xml_tree), xml_namespaces)


class TestXPathGeneration(unittest.TestCase):

    def test_node_xpaths_no_namespace(self):
        root = etree.fromstring(sample_no_namespace)
        xml_tree = etree.ElementTree(root)
        xpath_set = {XPath('/catalog/book[1]'),
                     XPath('/catalog/book[1]/@id'), XPath('/catalog/book[1]/author'), XPath('/catalog/book[1]/title'), XPath('/catalog/book[1]/genre'),
                     XPath('/catalog/book[1]/price'), XPath('/catalog/book[1]/publish_date'), XPath('/catalog/book[1]/description'),
                     XPath('/catalog/book[2]'),
                     XPath('/catalog/book[2]/@id'), XPath('/catalog/book[2]/author'), XPath('/catalog/book[2]/title'), XPath('/catalog/book[2]/genre'),
                     XPath('/catalog/book[2]/price'), XPath('/catalog/book[2]/publish_date'), XPath('/catalog/book[2]/description')}
        with self.subTest():
            self.assertCountEqual(xpath_set, generate_node_xpaths(xml_tree))
        with self.subTest():
            self.assertSetEqual(xpath_set, set(generate_node_xpaths(xml_tree)))

    def test_node_xpaths_with_namespaces(self):
        xml_namespaces = {None: 'http://www.iata.org/IATA/2007/00',
                          'ba': 'http://baplc.com/extensionSchema',
                          'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        root = etree.fromstring(sample_with_default_namespace)
        xml_tree = etree.ElementTree(root)
        raw_xpaths = {'/IATA_AIDX_FlightLegNotifRQ/Originator', '/IATA_AIDX_FlightLegNotifRQ/Originator/@CompanyShortName',
                    '/IATA_AIDX_FlightLegNotifRQ/DeliveringSystem', '/IATA_AIDX_FlightLegNotifRQ/DeliveringSystem/@CompanyShortName',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/Airline', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/Airline/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/FlightNumber', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/DepartureAirport',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/DepartureAirport/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/ArrivalAirport',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/ArrivalAirport/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/OriginDate', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegIdentifier/RepeatNumber',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[1]',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[1]/@RepeatIndex',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[1]/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[2]',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[2]/@RepeatIndex',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OperationalStatus[2]/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/ServiceType', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OwnerAirline',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/OwnerAirline/Airline', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/AircraftInfo',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/AircraftInfo/AircraftType',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/LegData/AircraftInfo/Registration', '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/TPA_Extension',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/TPA_Extension/ba:FlightCrewAirline',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/TPA_Extension/ba:FlightCrewAirline/@CodeContext',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/TPA_Extension/ba:CabinCrewAirline',
                    '/IATA_AIDX_FlightLegNotifRQ/FlightLeg/TPA_Extension/ba:CabinCrewAirline/@CodeContext'}
        expected = set(map(lambda x: XPath(x), raw_xpaths))
        with self.subTest():
            self.assertCountEqual(expected, generate_node_xpaths(xml_tree, xml_namespaces=xml_namespaces))
        with self.subTest():
            self.assertSetEqual(expected, set(generate_node_xpaths(xml_tree, xml_namespaces=xml_namespaces)))

if __name__ == '__main__':
    unittest.main()
