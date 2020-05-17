import json
import warnings
from types import CodeType

from etk.wikidata.utils import parse_datetime_string
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed

from backend_code.t2wml_exceptions import T2WMLException, make_frontend_err_dict
import backend_code.t2wml_exceptions as T2WMLExceptions
from backend_code.parsing.classes import ReturnClass
from backend_code.parsing.constants import char_dict
from backend_code.parsing.t2wml_parser import iter_on_n_for_code
from backend_code.spreadsheets.conversions import to_excel

from backend_code.triple_generator import generate_triples
from backend_code.utility_functions import translate_precision_to_integer, get_property_type


def parse_time_for_dict(response, sparql_endpoint):
    
    if "property" in response:
        try:
            prop_type= get_property_type(response["property"], sparql_endpoint)
        except QueryBadFormed:
            raise ValueError("The value given for property is not a valid property:" +str(response["property"]))
        
        if prop_type=="Time":
            if "format" in response:
                with warnings.catch_warnings(record=True) as w: #use this line to make etk stop harassing us with "no lang features detected" warnings
                    try:
                        datetime_string, precision = parse_datetime_string(str(response["value"]),
                                                                            additional_formats=[
                                                                                response["format"]])
                    except ValueError:
                        raise ValueError("Attempting to parse datetime string that isn't a datetime:" + str(response["value"]))

                    if "precision" not in response:
                        response["precision"] = int(precision.value.__str__())
                    else:
                        response["precision"] = translate_precision_to_integer(response["precision"])
                    response["value"] = datetime_string

def resolve_cell(yaml_object, col, row):
    sparql_endpoint=yaml_object.sparql_endpoint
    context={"t_var_row":int(row), "t_var_col":char_dict[col]}
    try:
        item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(yaml_object.eval_template, context)
        statement=get_template_statement(yaml_object.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
        if statement:
            data = {'statement': statement, 'error': None}
        else:
            data = {'statement': None, 'error': "Item doesn't exist"}
    except T2WMLException as exception:
        error = dict()
        error["errorCode"], error["errorTitle"], error["errorDescription"] = exception.args
        data = {'error': error}
    except Exception as exception:
        print(exception)
        raise exception
    return data


def get_template_statement(template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint):
    if item_parsed:
        template["item"]=item_parsed.value
        template["cell"]=to_excel(item_parsed.col, item_parsed.row)
    if value_parsed:
        template["value"]=value_parsed.value
    
    attributes={"qualifier": qualifiers_parsed, "reference": references_parsed}
    for attribute_name in attributes:
        attribute=attributes[attribute_name]
        if attribute:
            for attribute_dict in attribute:
                q_val=attribute_dict.pop("value") #deal with value last
                for key in attribute_dict:
                    if isinstance(attribute_dict[key], ReturnClass):
                        attribute_dict[key]=attribute_dict[key].value
                
                attribute_dict["value"]=q_val #add q_val back, then deal with it
                if q_val:
                    if isinstance(q_val, ReturnClass):
                        attribute_dict["value"]=q_val.value
                        attribute_dict["cell"]=to_excel(q_val.col, q_val.row)
                
                parse_time_for_dict(attribute_dict, sparql_endpoint)    

            template[attribute_name]=attribute

    parse_time_for_dict(template, sparql_endpoint)
    return template


def _evaluate_template_for_list_of_dicts(attributes, context):
    attributes_parsed=[]
    for attribute in attributes:
        new_dict=dict(attribute)
        for key in attribute:
            if isinstance(attribute[key], CodeType):
                q_parsed=iter_on_n_for_code(attribute[key], context)
                new_dict[key]=q_parsed
        attributes_parsed.append(new_dict)
    return attributes_parsed


def evaluate_template(template, context):
    item=template.get("item", None)
    value=template.get("value", None)
    qualifiers=template.get("qualifier", None)
    references=template.get("reference", None)

    item_parsed=value_parsed=qualifiers_parsed=references_parsed=None


    if item:
        item_parsed= iter_on_n_for_code(item, context)

    if value:
        value_parsed= iter_on_n_for_code(value, context)
    
    if qualifiers:
        qualifiers_parsed = _evaluate_template_for_list_of_dicts(qualifiers, context)
    
    if references:
        references_parsed = _evaluate_template_for_list_of_dicts(references, context)
        
    
    return item_parsed, value_parsed, qualifiers_parsed, references_parsed

    
    

def update_highlight_data(data, item_parsed, qualifiers_parsed, references_parsed):
    if item_parsed:
        item_cell=to_excel(item_parsed.col, item_parsed.row)
        if item_cell:
            data["item"].add(item_cell)
    
    
    attributes_parsed_dict= {'qualifierRegion': qualifiers_parsed, 'referenceRegion': references_parsed}
    for label, attributes_parsed in attributes_parsed_dict.items():
        if attributes_parsed:
            attribute_cells = set()
            for attribute in attributes_parsed:
                attribute_parsed=attribute.get("value", None)
                if attribute_parsed and isinstance(attribute_parsed, ReturnClass):
                    attribute_cell=to_excel(attribute_parsed.col, attribute_parsed.row)
                    if attribute_cell:
                        attribute_cells.add(attribute_cell)
            data[label] |= attribute_cells


def highlight_region(yaml_object):
    sparql_endpoint=yaml_object.sparql_endpoint
    if yaml_object.use_cache:
        data=yaml_object.cacher.get_highlight_region()
        if data:
            return data

    highlight_data = {"dataRegion": set(), "item": set(), "qualifierRegion": set(), 'referenceRegion': set(), 'error': dict()}
    statement_data=[]
    for col, row in yaml_object.region:
        cell=to_excel(col-1, row-1)
        highlight_data["dataRegion"].add(cell)
        context={"t_var_row":row, "t_var_col":col}
        try:
            item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(yaml_object.eval_template, context)
            update_highlight_data(highlight_data, item_parsed, qualifiers_parsed, references_parsed)

            if yaml_object.use_cache:
                    statement=get_template_statement(yaml_object.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
                    if statement:
                        statement_data.append(
                            {'cell': cell, 
                            'statement': statement})
        except T2WMLException as exception:
            error = dict()
            error["errorCode"], error["errorTitle"], error["errorDescription"] = exception.args
            data['error'][to_excel(col, row)] = error
        except Exception as exception:
            print(exception)
            data['error'][to_excel(col, row)]=make_frontend_err_dict(exception)
        
    highlight_data['dataRegion'] = list(highlight_data['dataRegion'])
    highlight_data['item'] = list(highlight_data['item'])
    highlight_data['qualifierRegion'] = list(highlight_data['qualifierRegion'])
    highlight_data['referenceRegion'] = list(highlight_data['referenceRegion'])

    if yaml_object.use_cache:
        yaml_object.cacher.save(highlight_data, statement_data)
    return highlight_data



def generate_download_file(yaml_object, filetype):
    sparql_endpoint=yaml_object.sparql_endpoint
    response=dict()
    data=[]
    if yaml_object.use_cache:
        data=yaml_object.cacher.get_download()

    if not data:
        error=[]
        for col, row in yaml_object.region:
            try:
                context={"t_var_row":row, "t_var_col":col}
                item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(yaml_object.eval_template, context)
                statement=get_template_statement(yaml_object.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
                if statement:
                    data.append(
                        {'cell': to_excel(col-1, row-1), 
                        'statement': statement})
            except Exception as e:
                error.append({'cell': to_excel(col, row), 
                'error': str(e)})


    if filetype == 'json':
        response["data"] = json.dumps(data, indent=3)
        response["error"] = None
        return response
    
    elif filetype == 'ttl':
        try:
            response["data"] = generate_triples("n/a", data, sparql_endpoint, created_by=yaml_object.created_by)
            response["error"] = None
            return response
        except Exception as e:
            print(e)
            response = {'error': str(e)}
            return response
