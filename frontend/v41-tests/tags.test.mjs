import test from 'node:test';
import assert from 'node:assert/strict';
import {validV41Tag,hasV41NonPrintable} from '../lib/v41-tags.mjs';
test('tag entry rejects control, format and non-ASCII separators while preserving printable text',()=>{
 for(const value of ['中文','春季 sale','😀','=SUM(A1)'])assert.equal(validV41Tag(value),true,value);
 for(const value of ['', ' padded ', 'a\u0000b', 'a\u200bb', 'a\u00a0b', 'a\nb'])assert.equal(validV41Tag(value),false,JSON.stringify(value));
});

test('nonprinting characters are rejected before outer whitespace normalization',()=>{
 assert.equal(hasV41NonPrintable('  good  '),false);
 assert.equal(hasV41NonPrintable('\tgood'),true);
 assert.equal(hasV41NonPrintable('good\n'),true);
});
