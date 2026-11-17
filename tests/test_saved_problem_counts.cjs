'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
function actualHelper(state){
  const start=source.indexOf('  function mergeSavedProblem('),end=source.indexOf('  function showSyncError(',start);
  assert.ok(start>=0&&end>start);
  let renders=0;
  const context=vm.createContext({state,renderCounts:()=>renders++});
  vm.runInContext(source.slice(start,end),context);
  return {save:problem=>context.mergeSavedProblem(problem),renders:()=>renders};
}
test('actual save helper adds to empty state and renders counts',()=>{
  const state={problems:[],contests:[],algorithms:[]},helper=actualHelper(state);
  helper.save({id:'first'});assert.equal(state.problems.length,1);assert.equal(helper.renders(),1);
});
test('missing, null, empty and dangling associations do not inflate existing groups',()=>{
  const state={problems:[{id:'missing'},{id:'null',contest_id:null,algorithm_id:null},{id:'empty',contest_id:'',algorithm_id:''},{id:'dangling',contest_id:'gone',algorithm_id:'gone'}],contests:[{id:'c',problem_count:99}],algorithms:[{id:'a',problem_count:99}]};
  actualHelper(state).save({id:'new'});
  assert.equal(state.contests[0].problem_count,0);assert.equal(state.algorithms[0].problem_count,0);
});
test('reassignment updates old and new groups without duplicating the saved record',()=>{
  const state={problems:[{id:'p',contest_id:'c1',algorithm_id:'a1'},{id:'q',contest_id:'c1',algorithm_id:'a2'}],contests:[{id:'c1'},{id:'c2'}],algorithms:[{id:'a1'},{id:'a2'}]},helper=actualHelper(state);
  helper.save({id:'p',contest_id:'c2',algorithm_id:'a2'});
  assert.equal(state.problems.length,2);assert.deepEqual(state.contests.map(c=>c.problem_count),[1,1]);assert.deepEqual(state.algorithms.map(a=>a.problem_count),[0,2]);
});
test('association counting scales with problems independently of group count',()=>{
  let reads=0;
  const problems=Array.from({length:200},(_,i)=>({id:String(i),get contest_id(){reads++;return 'c0';},get algorithm_id(){reads++;return 'a0';}}));
  const state={problems,contests:Array.from({length:100},(_,i)=>({id:'c'+i})),algorithms:Array.from({length:100},(_,i)=>({id:'a'+i}))};
  actualHelper(state).save({id:'new'});
  assert.equal(state.contests[0].problem_count,200);assert.equal(state.algorithms[0].problem_count,200);assert.ok(reads<=200*6,`association reads: ${reads}`);
});
