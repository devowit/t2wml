import os
import yaml
import sys
from pathlib import Path
CWD = os.getcwd()
from Code.utility_functions import get_property_type
# sys.path.insert(0, Path(CWD + "/etk"))
from etk.etk import ETK
from etk.knowledge_graph.schema import KGSchema
from etk.etk_module import ETKModule
from etk.wikidata.entity import WDProperty, WDItem
from etk.wikidata.value import Datatype, Item, Property, StringValue, URLValue, TimeValue, QuantityValue, MonolingualText, ExternalIdentifier, GlobeCoordinate
from etk.wikidata import serialize_change_record


def model_data():
	stream = open(Path.cwd().parent / "Datasets/data.worldbank.org/new_items_properties.yaml", 'r')
	yaml_data = yaml.safe_load(stream)
	# initialize
	kg_schema = KGSchema()
	kg_schema.add_schema('@prefix : <http://isi.edu/> .', 'ttl')
	etk = ETK(kg_schema=kg_schema, modules=ETKModule)
	doc = etk.create_document({}, doc_id="http://isi.edu/default-ns/projects")

	# bind prefixes
	doc.kg.bind('wikibase', 'http://wikiba.se/ontology#')
	doc.kg.bind('wd', 'http://www.wikidata.org/entity/')
	doc.kg.bind('wdt', 'http://www.wikidata.org/prop/direct/')
	doc.kg.bind('wdtn', 'http://www.wikidata.org/prop/direct-normalized/')
	doc.kg.bind('wdno', 'http://www.wikidata.org/prop/novalue/')
	doc.kg.bind('wds', 'http://www.wikidata.org/entity/statement/')
	doc.kg.bind('wdv', 'http://www.wikidata.org/value/')
	doc.kg.bind('wdref', 'http://www.wikidata.org/reference/')
	doc.kg.bind('p', 'http://www.wikidata.org/prop/')
	doc.kg.bind('pr', 'http://www.wikidata.org/prop/reference/')
	doc.kg.bind('prv', 'http://www.wikidata.org/prop/reference/value/')
	doc.kg.bind('prn', 'http://www.wikidata.org/prop/reference/value-normalized/')
	doc.kg.bind('ps', 'http://www.wikidata.org/prop/statement/')
	doc.kg.bind('psv', 'http://www.wikidata.org/prop/statement/value/')
	doc.kg.bind('psn', 'http://www.wikidata.org/prop/statement/value-normalized/')
	doc.kg.bind('pq', 'http://www.wikidata.org/prop/qualifier/')
	doc.kg.bind('pqv', 'http://www.wikidata.org/prop/qualifier/value/')
	doc.kg.bind('pqn', 'http://www.wikidata.org/prop/qualifier/value-normalized/')
	doc.kg.bind('skos', 'http://www.w3.org/2004/02/skos/core#')
	doc.kg.bind('prov', 'http://www.w3.org/ns/prov#')
	doc.kg.bind('schema', 'http://schema.org/')

	type_map = {
		'quantity': Datatype.QuantityValue,
		'url': URLValue
	}
	for k, v in yaml_data.items():
		p = WDProperty(k, type_map[v['type']], creator='http://www.isi.edu/t2wml')
		for lang, value in v['label'].items():
			for val in value:
				p.add_label(val, lang=lang)
		for lang, value in v['description'].items():
			for val in value:
				p.add_description(val, lang=lang)
		for pnode, items in v['statements'].items():
			for item in items:
				if pnode == 'P1896':
					p.add_statement(pnode, URLValue(item['value']))
				else:
					p.add_statement(pnode, Item(item['value']))
		doc.kg.add_subject(p)

	with open(Path.cwd().parent / "new_properties/result.ttl", "w") as f:
		data = doc.kg.serialize('ttl')
		f.write(data)


model_data()
with open(Path.cwd().parent / "new_properties/changes.tsv", "w") as fp:
	serialize_change_record(fp)

