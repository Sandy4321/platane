from datetime import datetime, timedelta
import simplex
from copy import copy
from pprint import pprint   

# constants for resolution and period
day=0
week=1
month=2

'''
Calculate a schedule for the given tasks.
Returns a result structure: {
start: <datetime>,
slots: [   ],
schedule : [
   { task : <taskname>, 
     slots : [ ] }
]
'''
def schedule_tasks(tasks, period=week, resolution=day, work=True):
    start_date, slots, prio_items = itemize(tasks, resolution, work)
    s = {}
    all_items = {}  # store all generated items for later sorting
    base_slots = copy(slots) # slots for calculating discrete load
    for priority in sorted(prio_items.keys()):
        items = prio_items[priority]    
        items = discretize_load(items, base_slots, start_date, period)
        #items = consolidate_related(items, s)
        all_items.update(items)
        s.update(schedule(items, slots, slot_size(resolution, work)))    
        if priority < 0:
            base_slots = copy(slots)
    result = []
    # sort the items and gathers the splitted tasks
    split_treated = set()
    for name in sort_schedule(all_items.values(), s):
        if name.endswith(']'): 
            orig_name = name.split(' [')[0]
            if orig_name not in split_treated:
                split_treated.add(orig_name)
            else:
                continue
            summed_slots = len(slots)*[0]
            summed_effort = 0
            for item in all_items.values():            
                sub_item = item['name']
                if sub_item.startswith(orig_name):
                    # ignore items in overflow
                    if round(item['effort'],3) != round(sum(s[sub_item]),3):
                        result.append( (sub_item, s[sub_item], all_items[sub_item]['effort'], sum(s[sub_item])))
                        continue
                    summed_effort = summed_effort+item['effort']
                    for i in range(len(slots)):
                        summed_slots[i]=summed_slots[i]+s[sub_item][i]
            result.append( (orig_name, summed_slots, summed_effort, sum(summed_slots) ))                       
        else:
            result.append( (name, s[name], all_items[name]['effort'], sum(s[name]))) 
    return start_date, slots, result
    
'''
Sort the items in order of appearance. Returns the name list.
'''
def sort_schedule(items, schedule):
    s = []
    for i in items:
        j = -1
        slots = schedule[i['name']]
        start = -1
        end = 0
        for j in range(len(slots)):
            if start == -1 and slots[j] > 0:
                start = j
            if slots[j] > 0:
                end = j
        s.append( ( i['priority'], start, end, i['name'] ) )
    s.sort()
    return [ k[3] for k in s ]
    
'''
Schedule the given items into the slots, updates the slots
'''
def schedule(items, slots, size):
    sorted_items = sorted( list(items.values()), key=lambda item: (item['from'], item['to']))
    A, b, edges = generate_matrix(sorted_items, slots, size)
    optimum = calculate(A, b)
    s = {}
    for name in items.keys():
        s[name] = [0]*len(slots)
    for i in range(0, len(edges)):
        s[edges[i][0]][edges[i][1]]=optimum[i]
        slots[edges[i][1]] = slots[edges[i][1]]-optimum[i]
    return s
    
'''
Prepare the Ax <= b matrix and vector. Also provide the corresponsing edges (task, slot)
'''
def generate_matrix(items, slots, size):
    edges = []
    A = []    
    b = []
    # variable count
    n = 0
    for item in items:        
        n = n + (item['to']-item['from']) + 1
    pos = 0
    slot_usage = {}
    # constraints on task effort
    for item in items:        
        line = [0]*n
        for i in range(item['from'], item['to']+1):            
            edges.append( ( item['name'], i ) )
            if not slot_usage.has_key(i):
                slot_usage[i] = []
            slot_usage[i].append(pos)
            line[pos] = 1.0
            pos += 1
        A.append(line)
        b.append(item['effort'])
    # constraints on slot capacity
    for i in sorted( slot_usage.keys() ):
        line = [0]*n
        for p in slot_usage[i]:
            line[p] = 1.0
        A.append(line)
        b.append(slots[i])        
    return A, b, edges    
    
'''
Delegate to simplex algorithm to optimize the planning.
'''
def calculate(A, b):
    n=len(A[0])
    f=[-1.0]*n
    constraints=[]
    for i in range(0, len(A)):
        constraints.append( ( A[i], b[i] ) )
    return simplex.simplex(f, constraints)
    
'''
Transform the task list in schedulable items and compute slots.
Returns a schedulable structure: {
    start_date: <datetime>,
    slots: [ ],
    slot_size
    items: { <int>, items [ ] }
}
'''
def itemize(tasks, resolution, work=True):
    start, end = bounds(tasks, resolution)
    slots = []
    items = {}
    i = 0
    for d in calendar(start, end, resolution):        
        for t in tasks:
            if t.has_key('priority'):
                priority = t['priority']
            else:
                priority = 0
            if not items.has_key(priority):
                items[priority] = {}
            if not items[priority].has_key(t['name']):
                items[priority][t['name']] = {}
            item = items[priority][t['name']]
            item['name'] = t['name']
            item['priority'] = priority
            if t.has_key('effort'):
                item['effort'] = t['effort']
            if t.has_key('load'):
                item['load'] = t['load']
            if t['from'] >= d:
                item['from'] = i
            if t['to'] >= d:
                item['to'] = i      
        i += 1
        slots.append(slot_size(resolution, work))
    return start, slots, items
    
'''
Split load-based task into effort-based tasks according to the period.
'''
def discretize_load(items, slots, start_date, period):
    new_items = copy(items)
    for k,item in items.iteritems():
        if item.has_key('load') and item['load'] > 0:        
            load = item['load']
            capacity = 0
            new_item = None
            i=0
            for d in calendar(start_date, size=len(slots)): 
                if period == week:
                    start = (d.weekday() == 0)             
                if period == month:
                    start = (d.day == 1)
                if start and new_item or i == len(slots)-1:
                    # close the new item
                    new_item['to'] = i-1
                    new_item['name'] = new_item['name']+"]"
                    new_items[new_item['name']] = new_item
                    if i==len(slots)-1:
                        new_item['effort'] = new_item['effort'] + load * slots[i]    
                    new_item = None
                if not new_item:
                    new_item = copy(item)
                    new_item['name'] = item['name']+" ["+str(d.isocalendar()[1])
                    new_item['to'] = None
                    new_item['effort'] = 0
                    new_item['from'] = i
                new_item['effort'] = new_item['effort'] + load * slots[i]
                i+=1
            del new_items[k]
    return new_items
    
'''
Substract item schedules from main item
'''    
def consolidate_related(items, schedule):
    # TODO: implement
    return items
    
'''
Returns the first from-date and last to-date of all tasks
'''
def bounds(tasks, resolution):
    s = datetime(2100,01,01)
    e = datetime(2000,01,01)
    for t in tasks:
        if t['from'] < s:
            s = t['from']
        if t['to'] > e:
            e = t['to']
    return s, e
    
'''
Generator of a calendar from the given date.
'''
def calendar(from_date, to_date=datetime(2100, 01, 01), size=None, resolution=day, work=True):
    d = from_date
    s = 0
    while True:
        while work and d.weekday() == 5 or d.weekday() == 6:
            d = d + timedelta(1)
        yield d
        d = d + timedelta(1)
        s+=1
        if (size and s >= size ) or d > to_date:
            break
    # TODO: resolution week
    
'''
Defines the slot size according to the chosen resolution.
'''
def slot_size(resolution, work=True):
    if resolution == day:
        return 1.0
    if resolution == week:
        return 5.0 if work else 7.0
        
        
if __name__ == '__main__':
            
    tasks = [ 
        { 'name' : 'absence', 'priority':-1, 'effort': 3, 'from':datetime(2011, 05, 24), 'to':datetime(2011, 05, 26) },
        { 'name' : 'architecture', 'effort': 5, 'from':datetime(2011, 05, 18), 'to':datetime(2011, 06, 8) },        
        { 'name' : 'management', 'load': 0.25, 'from':datetime(2011, 05, 18), 'to':datetime(2011, 06, 10) },        
        { 'name' : 'project1', 'priority': 0, 'effort': 3.5, 'from':datetime(2011, 05, 20), 'to':datetime(2011, 06, 13) },
        { 'name' : 'project2', 'effort': 3.5, 'from':datetime(2011, 05, 23), 'to':datetime(2011, 06, 10) },
        { 'name' : 'partial time', 'priority': -1, 'load': 0.1, 'from':datetime(2011, 05, 18), 'to':datetime(2011, 06, 13) }]
        
         
    start, slots, sched = schedule_tasks(tasks)
    dates = [ c for c in calendar(start, size=len(slots)) ]
    slots = [ 1.0-v for v in slots ]

    import visualize
    print visualize.render(dates, slots, sched)