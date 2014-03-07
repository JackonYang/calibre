#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2014, Kovid Goyal <kovid at kovidgoyal.net>'

from unicodedata import normalize

from itertools import izip
from future_builtins import map

from calibre.constants import plugins
from calibre.utils.icu import primary_sort_key, find

DEFAULT_LEVEL1 = '/'
DEFAULT_LEVEL2 = '-_ 0123456789'
DEFAULT_LEVEL3 = '.'

class Matcher(object):

    def __init__(self, items, level1=DEFAULT_LEVEL1, level2=DEFAULT_LEVEL2, level3=DEFAULT_LEVEL3):
        items = map(lambda x: normalize('NFC', unicode(x)), filter(None, items))
        items = tuple(map(lambda x: x.encode('utf-8'), items))
        sort_keys = tuple(map(primary_sort_key, items))

        speedup, err = plugins['matcher']
        if speedup is None:
            raise RuntimeError('Failed to load the matcher plugin with error: %s' % err)
        self.m = speedup.Matcher(items, sort_keys, level1.encode('utf-8'), level2.encode('utf-8'), level3.encode('utf-8'))

    def __call__(self, query):
        query = normalize('NFC', unicode(query)).encode('utf-8')
        return map(lambda x:x.decode('utf-8'), self.m.get_matches(query))


def calc_score_for_char(ctx, prev, current, distance):
    factor = 1.0
    ans = ctx.max_score_per_char

    if prev in ctx.level1:
        factor = 0.9
    elif prev in ctx.level2 or (icu_lower(prev) == prev and icu_upper(current) == current):
        factor = 0.8
    elif prev in ctx.level3:
        factor = 0.7
    else:
        factor = (1.0 / distance) * 0.75

    return ans * factor

def process_item(ctx, haystack, needle):
    # non-recursive implementation using a stack
    stack = [(0, 0, 0, 0, [-1]*len(needle))]
    final_score, final_positions = stack[0][-2:]
    push, pop = stack.append, stack.pop
    while stack:
        hidx, nidx, last_idx, score, positions = pop()
        key = (hidx, nidx, last_idx)
        mem = ctx.memory.get(key, None)
        if mem is None:
            for i in xrange(nidx, len(needle)):
                n = needle[i]
                if (len(haystack) - hidx < len(needle) - i):
                    score = 0
                    break
                pos = find(n, haystack[hidx:])[0] + hidx
                if pos == -1:
                    score = 0
                    break

                distance = pos - last_idx
                score_for_char = ctx.max_score_per_char if distance <= 1 else calc_score_for_char(ctx, haystack[pos-1], haystack[pos], distance)
                hidx = pos + 1
                push((hidx, i, last_idx, score, list(positions)))
                last_idx = positions[i] = pos
                score += score_for_char
            ctx.memory[key] = (score, positions)
        else:
            score, positions = mem
        if score > final_score:
            final_score = score
            final_positions = positions
    return final_score, final_positions

class PyScorer(object):
    __slots__ = ('level1', 'level2', 'level3', 'max_score_per_char', 'items', 'memory')

    def __init__(self, items, level1=DEFAULT_LEVEL1, level2=DEFAULT_LEVEL2, level3=DEFAULT_LEVEL3):
        self.level1, self.level2, self.level3 = level1, level2, level3
        self.max_score_per_char = 0
        self.items = map(lambda x: normalize('NFC', unicode(x)), filter(None, items))

    def __call__(self, needle):
        for item in self.items:
            self.max_score_per_char = (1.0 / len(item) + 1.0 / len(needle)) / 2.0
            self.memory = {}
            yield process_item(self, item, needle)

class CScorer(object):

    def __init__(self, items, level1=DEFAULT_LEVEL1, level2=DEFAULT_LEVEL2, level3=DEFAULT_LEVEL3):
        items = tuple(map(lambda x: normalize('NFC', unicode(x)), filter(None, items)))

        speedup, err = plugins['matcher']
        if speedup is None:
            raise RuntimeError('Failed to load the matcher plugin with error: %s' % err)
        self.m = speedup.Matcher(items, unicode(level1), unicode(level2), unicode(level3))

    def __call__(self, query):
        query = normalize('NFC', unicode(query))
        scores, positions = self.m.calculate_scores(query)
        for score, pos in izip(scores, positions):
            yield score, pos

def test():
    items = ['m1mn34o/mno']
    s = PyScorer(items)
    c = CScorer(items)
    for q in (s, c):
        print (q)
        for item, (score, positions) in izip(items, q('mno')):
            print (item, score, positions)

def test_mem():
    from calibre.utils.mem import gc_histogram, diff_hists
    m = Matcher([])
    del m
    def doit(c):
        m = Matcher([c+'im/one.gif', c+'im/two.gif', c+'text/one.html',])
        m('one')
    import gc
    gc.collect()
    h1 = gc_histogram()
    for i in xrange(100):
        doit(str(i))
    h2 = gc_histogram()
    diff_hists(h1, h2)

if __name__ == '__main__':
    test()
    # m = Matcher(['image/one.png', 'image/two.gif', 'text/one.html'])
    # for q in ('one', 'ONE', 'ton', 'imo'):
    #     print (q, '->', tuple(m(q)))
    # test_mem()