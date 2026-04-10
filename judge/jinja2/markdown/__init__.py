import logging
import re
from urllib.parse import urlparse

from markdown_it import MarkdownIt
from bleach.css_sanitizer import CSSSanitizer
from bleach.sanitizer import Cleaner
from django.conf import settings
from django.utils.module_loading import import_string
from lxml import html
from lxml.etree import ParserError, XMLSyntaxError
from markupsafe import Markup

from judge.highlight_code import highlight_code
from judge.jinja2.markdown.lazy_load import lazy_load as lazy_load_processor
from judge.utils.camo import client as camo_client
from judge.utils.mathoid import MathoidMathParser, format_math
from judge.utils.texoid import TEXOID_ENABLED, TexoidRenderer
from .bleach_whitelist import all_styles, mathml_attrs, mathml_tags
from .. import registry

logger = logging.getLogger('judge.html')

NOFOLLOW_WHITELIST = settings.NOFOLLOW_EXCLUDED


cleaner_cache = {}
MATH_SEGMENT_RE = re.compile(r'(```[\s\S]*?```|`[^`\n]*`)')
DISPLAY_MATH_RE = re.compile(r'(?<!\\)\$\$(.+?)(?<!\\)\$\$', re.S)
INLINE_MATH_RE = re.compile(r'(?<![\\$])\$(?!\$)(.+?)(?<![\\$])\$(?!\$)', re.S)


def get_cleaner(name, params):
    if name in cleaner_cache:
        return cleaner_cache[name]

    styles = params.pop('styles', None)
    if styles:
        params['css_sanitizer'] = CSSSanitizer(allowed_css_properties=all_styles if styles is True else styles)

    if params.pop('mathml', False):
        params['tags'] = params.get('tags', []) + mathml_tags
        params['attributes'] = params.get('attributes', {}).copy()
        params['attributes'].update(mathml_attrs)

    cleaner = cleaner_cache[name] = Cleaner(**params)
    return cleaner


def fragments_to_tree(fragment):
    tree = html.Element('div')
    try:
        parsed = html.fragments_fromstring(fragment, parser=html.HTMLParser(recover=True))
    except (XMLSyntaxError, ParserError) as e:
        if fragment and (not isinstance(e, ParserError) or e.args[0] != 'Document is empty'):
            logger.exception('Failed to parse HTML string')
        return tree

    if parsed and isinstance(parsed[0], str):
        tree.text = parsed[0]
        parsed = parsed[1:]
    tree.extend(parsed)
    return tree


def strip_paragraphs_tags(tree):
    for p in tree.xpath('.//p'):
        for child in p.iterchildren(reversed=True):
            p.addnext(child)
        parent = p.getparent()
        prev = p.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or '') + p.text
        else:
            parent.text = (parent.text or '') + p.text
        parent.remove(p)


def fragment_tree_to_str(tree):
    return html.tostring(tree, encoding='unicode')[len('<div>'):-len('</div>')]


def inc_header(text, level):
    pattern = re.compile(
        r'<(\/?)h([1-9][0-9]*)>',
        re.X | re.M,
    )
    return re.sub(pattern, lambda x: '<' + x.group(1) + 'h' + str(int(x.group(2)) + level) + '>', text)


def add_table_class(text):
    return text.replace(r'<table>', r'<table class="table">')


def _render_code_block(code, language, attrs):
    if language:
        return str(highlight_code(code, language))
    return ''


def _add_nofollow(tree):
    for a in tree.xpath('.//a[@href]'):
        href = a.get('href')
        if not href:
            continue

        parsed = urlparse(href)
        # Relative URLs and anchors should not be marked nofollow.
        if not parsed.netloc:
            continue

        hostname = (parsed.hostname or '').lower()
        if hostname in NOFOLLOW_WHITELIST:
            continue

        rel_values = set((a.get('rel') or '').split())
        rel_values.add('nofollow')
        a.set('rel', ' '.join(sorted(rel_values)))


def _mark_spoilers(tree):
    # Keep support for markdown2-style spoiler blockquotes (`>! spoiler`).
    for blockquote in tree.xpath('.//blockquote'):
        first = blockquote[0] if len(blockquote) else None
        if first is None or first.tag != 'p':
            continue

        text = first.text or ''
        if not text.startswith('!'):
            continue

        first.text = text[1:].lstrip()
        classes = set((blockquote.get('class') or '').split())
        classes.add('spoiler')
        blockquote.set('class', ' '.join(sorted(classes)))


def _render_math(segment, math_parser):
    segment = DISPLAY_MATH_RE.sub(lambda m: math_parser.display_math(m.group(1).strip()), segment)
    return INLINE_MATH_RE.sub(lambda m: math_parser.inline_math(m.group(1).strip()), segment)


def _render_plain_tex_math(segment):
    segment = DISPLAY_MATH_RE.sub(lambda m: '$$%s$$' % format_math(m.group(1).strip()), segment)
    return INLINE_MATH_RE.sub(lambda m: '~%s~' % format_math(m.group(1).strip()), segment)


def _apply_math(text, math_engine):
    if not text or not math_engine:
        return text

    parser_engine = math_engine
    if not settings.MATHOID_URL and math_engine in ('mml', 'svg', 'jax'):
        # Without mathoid, keep TeX delimiters for client-side MathJax rendering.
        parser_engine = 'tex'

    if parser_engine == 'tex':
        renderer = _render_plain_tex_math
    elif parser_engine in MathoidMathParser.types:
        math_parser = MathoidMathParser(parser_engine)
        renderer = lambda segment: _render_math(segment, math_parser)
    else:
        return text

    parts = MATH_SEGMENT_RE.split(text)
    for i, part in enumerate(parts):
        if not part:
            continue
        if MATH_SEGMENT_RE.fullmatch(part):
            continue
        parts[i] = renderer(part)
    return ''.join(parts)


@registry.filter
def markdown(text, style, math_engine=None, lazy_load=False, strip_paragraphs=False):
    styles = settings.MARKDOWN_STYLES.get(style, settings.MARKDOWN_DEFAULT_STYLE)
    safe_mode = styles.get('safe_mode', True)

    bleach_params = styles.get('bleach', {})

    post_processors = []
    if hasattr(settings, 'POST_PROCESSORS'):
        for name, path in settings.POST_PROCESSORS.items():
            try:
                post_processors.append(import_string(path))
            except ImportError:
                logger.warning('Failed to import post processor %s', path)

    if styles.get('use_camo', False) and camo_client is not None:
        post_processors.append(camo_client.update_tree)
    if styles.get('nofollow', True):
        post_processors.append(_add_nofollow)
    post_processors.append(_mark_spoilers)
    if lazy_load:
        post_processors.append(lazy_load_processor)

    markdown_parser = MarkdownIt(
        'commonmark',
        options_update={
            'html': not safe_mode,
            'breaks': False,
            'highlight': _render_code_block,
        },
    ).enable('table').enable('strikethrough')

    text = _apply_math(text, math_engine)
    result = markdown_parser.render(text)

    result = add_table_class(result)
    result = inc_header(result, 2)

    if post_processors or strip_paragraphs:
        tree = fragments_to_tree(result)
        for processor in post_processors:
            processor(tree)
        if strip_paragraphs:
            strip_paragraphs_tags(tree)
        result = fragment_tree_to_str(tree)
    if bleach_params:
        result = get_cleaner(style, bleach_params).clean(result)
    return Markup(result)
