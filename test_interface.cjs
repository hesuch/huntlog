const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8').split('document.addEventListener("click",async event=>{')[0];
const ctx={Intl,URLSearchParams,localStorage:{getItem:()=>null}};vm.createContext(ctx);vm.runInContext(source,ctx);
vm.runInContext(`
state.stats={kills:7,rare_kills:1,kills_per_hour:7,tracked_hunts:1,count:1,defeated:[
 {name:'Aron',count:3,rare_count:0,battle_group:'pokemon'},
 {name:'Shiny Gengar',count:1,rare_count:1,battle_group:'pokemon'},
 {name:'Noctu',count:2,rare_count:0,battle_group:'dungeon'},
 {name:'Boss Giant Ghost',count:1,rare_count:0,battle_group:'boss',image_name:"Lavender's Curse"}]};
globalThis.results={};
for(const tab of ['normal','rare','dungeon','boss']){state.battleTab=tab;results[tab]=defeatedPanel(state.stats,true);}
state.customImages.bossgiantghost='data:image/png;base64,test';
globalThis.custom=sprite("Lavender's Curse",true,'Boss Giant Ghost');
state.draft={category:'terror',location:'Terror',duration:60,extras:0,boss_rules:{terror:[],unique:[],dungeons:{},images:{bossgiantghost:"Lavender's Curse"}},
enemies:[{name:'Boss Giant Ghost',count:1,reported_count:1,included:true},{name:'Gastly',count:0,reported_count:7,included:true}],
items:[{kind:'drop',name:'Ghostly loot bag (Expert)',count:1,included:true,price:0},{kind:'supply',name:'Spell tag',count:8,included:true,price:1}]};
recomputeDraft();globalThis.first=JSON.stringify(state.draft);recomputeDraft();globalThis.second=JSON.stringify(state.draft);
state.draft.category='mixed';state.draft.items[1].included=false;recomputeDraft();globalThis.restored=state.draft.enemies[1].count;
`,ctx);
for(const [tab,name] of Object.entries({normal:'Aron',rare:'Shiny Gengar',dungeon:'Noctu',boss:'Boss Giant Ghost'})){
 const body=ctx.results[tab].split('class="encounter-grid">')[1];assert(body.includes(name));
 for(const other of ['Aron','Shiny Gengar','Noctu','Boss Giant Ghost'].filter(n=>n!==name))assert(!body.includes(other));
}
assert(ctx.custom.includes('data:image/png;base64,test'));assert.equal(ctx.first,ctx.second);assert.equal(ctx.restored,7);
assert(!source.includes('data-field="server"'));assert(!source.includes('data-field="pokemon"'));
console.log('Interface: four exclusive tabs, contextual custom art, ghost preview, repeated calculation and removed fields OK');
