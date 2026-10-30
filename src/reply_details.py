"""Extract explicitly labeled, quoted customer fields without an LLM or guessing."""

import re

LABELS={'address':'address','pata':'address','पता':'address',
        'name':'name','naam':'name','नाम':'name'}
FIELD=re.compile(r'(?<!\w)(address|pata|पता|name|naam|नाम)(?!\w)',re.I)
PREFIX=re.compile(r'^(address|pata|पता|name|naam|नाम)\s*:\s*(.*)$',re.I|re.S)


def parse_detail_reply(text):
    """Return field->literal value, None for ordinary chat, or reject ambiguity.

    Natural prose requires a label and double quotes for each field. Existing
    single-field ADDRESS:/NAME: commands remain supported. Text inside values
    is never interpreted as another field, intent, or executable instruction.
    """
    normalized=text.translate(str.maketrans({'“':'"','”':'"'}))
    if '"' not in normalized:
        match=PREFIX.fullmatch(normalized.strip())
        if match:
            value=match[2].strip()
            if not value or re.search(r'(?<!\w)(?:address|name|pata|naam|पता|नाम)\s*:',value,re.I):
                raise ValueError('Ambiguous or empty detail command.')
            return {LABELS[match[1].casefold()]:value}
        if FIELD.search(normalized):
            raise ValueError('Put the value after each field label in double quotes.')
        return None
    if normalized.count('"')%2:
        raise ValueError('Close every double quote.')
    quotes=list(re.finditer(r'"([^\"]*)"',normalized,re.S))
    masked=list(normalized)
    for quote in quotes:
        masked[quote.start():quote.end()]=' '*(quote.end()-quote.start())
    labels=list(FIELD.finditer(''.join(masked)))
    if not labels:
        # A quoted YES/NO/PAID is not a correction and never an intent.
        return None
    result={}
    previous_end=0
    consumed=0
    for quote in quotes:
        preceding=[label for label in labels if previous_end<=label.start()<quote.start()]
        if len(preceding)!=1:
            raise ValueError('Each quoted value needs exactly one name or address label.')
        field=LABELS[preceding[0][1].casefold()]
        if field in result:
            raise ValueError('Provide each field only once.')
        value=quote[1].strip()
        if not value:
            raise ValueError('Quoted values cannot be empty.')
        result[field]=value
        consumed+=1
        previous_end=quote.end()
    if consumed!=len(labels):
        raise ValueError('Every named field must have a quoted value.')
    return result


def valid_detail_value(field,value):
    if not value or any(ord(char)<32 and char not in '\n\t' for char in value):
        return False
    if field=='address':
        return len(value)<=800
    return (field=='name' and len(value)<=150 and
            value.casefold() not in {'test','test order','asdf','xyz','dummy','abc'})


def address_has_delivery_details(value):
    """Existing conservative completeness check, separate from extraction/storage."""
    return len(value)>=12 and (bool(re.search(r'\d',value)) or (',' in value and len(value.split())>=4))
