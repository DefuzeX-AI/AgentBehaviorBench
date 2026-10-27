from utils.util_func import deep_merge_dicts

a = {'a': 1, 'b': 2, 'c': 3, "config": {"a": 1, "b": 2, "c": 3}}
b = {'a': 2, "config": {"a": 2, "d": 3, 'data': {"key": "value"}}}

c = deep_merge_dicts(a, b)
print(c)