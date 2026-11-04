import test from 'node:test';
import assert from 'node:assert/strict';
import {validV41Tag} from '../lib/v41-tags.mjs';
test('tag entry rejects control, format and non-ASCII separators while preserving printable text',()=>{
 for(const value of ['中文','春季 sale','😀','=SUM(A1)'])assert.equal(validV41Tag(value),true,value);
 for(const value of ['', ' padded ', 'a\u0000b', 'a\u200bb', 'a\u00a0b', 'a\nb'])assert.equal(validV41Tag(value),false,JSON.stringify(value));
});
