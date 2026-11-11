import {describe,it,expect,vi,afterEach} from 'vitest';
import {api,ApiError,mergeEvents,type Event} from './api';
afterEach(()=>vi.unstubAllGlobals());
describe('authenticated API boundary',()=>{
 it('sends cookies and an idempotency key for mutations',async()=>{const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({id:'run'})});vi.stubGlobal('fetch',fetch);await api('/executions',{topic:'Brief'});const [path,options]=fetch.mock.calls[0];expect(path).toBe('/api/executions');expect(options.credentials).toBe('include');expect(options.headers['Idempotency-Key']).toMatch(/^[a-f0-9-]{36}$/);expect(JSON.parse(options.body)).toEqual({topic:'Brief'});});
 it('preserves server errors and authentication status',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:401,json:async()=>({detail:'Session expired'})}));await expect(api('/auth/me')).rejects.toEqual(new ApiError(401,'Session expired'));});
 it('handles empty successful responses',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,status:204}));await expect(api('/auth/logout',{})).resolves.toBeUndefined();});
});
describe('event cursor merging',()=>{it('deduplicates polling overlap and preserves monotonic order',()=>{const event=(id:number)=>({id,message:`Event ${id}`} as Event);expect(mergeEvents([event(2),event(1)],[event(2),event(3)]).map(e=>e.id)).toEqual([1,2,3]);});});
