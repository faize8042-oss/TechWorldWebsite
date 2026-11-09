// Run the actual allowlisted browser scripts against a small DOM model offline.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const element = () => ({attrs:{}, events:{}, textContent:'', classes:new Set(), focused:false,
  setAttribute(k,v){this.attrs[k]=v}, getAttribute(k){return this.attrs[k]},
  addEventListener(k,fn){this.events[k]=fn}, contains(t){return t===this}, focus(){this.focused=true},
  get classList(){return {remove:k=>this.classes.delete(k),toggle:(k,on)=>on?this.classes.add(k):this.classes.delete(k)}}});
const menu=element(), nav=element(), link=element(), theme=element(), icon=element(), year=element();
nav.querySelectorAll=()=>[link];
const root={dataset:{}};
const document={documentElement:root,events:{}, addEventListener(k,fn){this.events[k]=fn},
  querySelector:s=>({'.menu-toggle':menu,'#primary-navigation':nav,'.theme-toggle':theme,'.theme-icon':icon,'#current-year':year}[s])};
const window={innerWidth:375,events:{},addEventListener(k,fn){this.events[k]=fn}};
const values={};
const localStorage={getItem:k=>values[k],setItem:(k,v)=>values[k]=v};
const context=vm.createContext({document,window,localStorage,Date});
for (const script of ['theme','navigation','main']) vm.runInContext(fs.readFileSync(path.join(__dirname,'site/assets/js',script+'.js'),'utf8'),context);
assert.equal(root.dataset.theme,'dark'); theme.events.click(); assert.equal(root.dataset.theme,'light');
assert.equal(values['tech-world-theme'],'light'); theme.events.click(); assert.equal(root.dataset.theme,'dark');
menu.events.click(); assert.equal(menu.attrs['aria-expanded'],'true'); assert(nav.classes.has('is-open'));
document.events.keydown({key:'Escape'}); assert.equal(menu.attrs['aria-expanded'],'false'); assert(menu.focused);
menu.events.click(); link.events.click(); assert(!nav.classes.has('is-open'));
menu.events.click(); document.events.click({target:{}}); assert(!nav.classes.has('is-open'));
menu.events.click(); window.innerWidth=1200; window.events.resize(); assert(!nav.classes.has('is-open'));
assert.equal(year.textContent,new Date().getFullYear());
console.log('PASS: actual scripts — theme, persistence, menu toggle, Escape/focus, links, outside click, desktop resize, footer year');
