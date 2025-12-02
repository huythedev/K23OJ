import re
import logging
from lxml import html
from judge.utils.mathoid import MathoidMathParser
from judge.utils.texoid import TexoidRenderer, TEXOID_ENABLED

logger = logging.getLogger('dmoj.post_processors')

def _process_content(text, pattern, callback):
    if not text:
        return None
    
    matches = list(pattern.finditer(text))
    if not matches:
        return None
        
    result_nodes = []
    last_idx = 0
    
    for match in matches:
        # Text before match
        pre_text = text[last_idx:match.start()]
        if pre_text:
            result_nodes.append(pre_text)
            
        # Replacement
        replacement_html = callback(match)
        if replacement_html is None:
            result_nodes.append(match.group(0))
        else:
            try:
                frags = html.fragments_fromstring(replacement_html)
                if not isinstance(frags, list):
                    frags = [frags]
                result_nodes.extend(frags)
            except Exception:
                logger.exception('Failed to parse replacement: %s', replacement_html)
                result_nodes.append(match.group(0))
            
        last_idx = match.end()
        
    # Remaining text
    if last_idx < len(text):
        result_nodes.append(text[last_idx:])
        
    return result_nodes

def _replace_in_node(node, pattern, callback):
    # Process node.text
    new_content = _process_content(node.text, pattern, callback)
    if new_content:
        first = new_content[0]
        if isinstance(first, str):
            node.text = first
            remaining = new_content[1:]
        else:
            node.text = None
            remaining = new_content
            
        elements_to_insert = []
        current_element = None
        
        for item in remaining:
            if isinstance(item, str):
                if current_element is not None:
                    current_element.tail = (current_element.tail or '') + item
                else:
                    node.text = (node.text or '') + item
            else:
                current_element = item
                elements_to_insert.append(item)
        
        for el in reversed(elements_to_insert):
            node.insert(0, el)

    # Process node.tail
    new_tail_content = _process_content(node.tail, pattern, callback)
    if new_tail_content:
        parent = node.getparent()
        if parent is not None:
            first = new_tail_content[0]
            if isinstance(first, str):
                node.tail = first
                remaining = new_tail_content[1:]
            else:
                node.tail = None
                remaining = new_tail_content
            
            elements_to_insert = []
            current_element = None
            
            for item in remaining:
                if isinstance(item, str):
                    if current_element is not None:
                        current_element.tail = (current_element.tail or '') + item
                    else:
                        node.tail = (node.tail or '') + item
                else:
                    current_element = item
                    elements_to_insert.append(item)
            
            index = parent.index(node) + 1
            for el in reversed(elements_to_insert):
                parent.insert(index, el)

def mathoid(tree):
    parser = MathoidMathParser('auto')
    pattern = re.compile(r'\\\[(.*?)\\\]|\\\((.*?)\\\)')
    
    def callback(match):
        display, inline = match.groups()
        if display is not None:
            return parser.display_math(display)
        else:
            return parser.inline_math(inline)

    for node in tree.iter():
        if node.tag in ('script', 'style', 'pre', 'code', 'textarea'):
            continue
        _replace_in_node(node, pattern, callback)

def latex(tree):
    if not TEXOID_ENABLED:
        return

    renderer = TexoidRenderer()
    pattern = re.compile(r'\[tex\](.*?)\[/tex\]', re.DOTALL)
    
    def callback(match):
        tex = match.group(1)
        import hashlib
        from judge.utils.unicode import utf8bytes
        h = hashlib.sha1(utf8bytes(tex)).hexdigest()
        
        data = renderer.query_texoid(tex, h)
        if data and data.get('success'):
            if 'svg' in data:
                return data['svg']
            elif 'png' in data:
                return f'<img src="{data["png"]}" alt="{tex}">'
        return match.group(0)

    for node in tree.iter():
        if node.tag in ('script', 'style', 'pre', 'code', 'textarea'):
            continue
        _replace_in_node(node, pattern, callback)
