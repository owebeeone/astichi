astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    events = []
    astichi_hole(body)

    @astichi_insert(body, ref=Pipeline.Root.Loop)
    def __astichi_contrib__Root__body__0__Loop():
        astichi_import(events, outer_bind=True)
        astichi_hole(slot__iter_0)

        @astichi_insert(slot__iter_0, ref=Pipeline.Root.Loop.Step0[0])
        def __astichi_contrib__Pipeline__slot__iter_0__0__Step0():
            astichi_import(__astichi_assign__inst__Pipeline__ref__Root__name__events, bound=True)
            __astichi_assign__inst__Pipeline__ref__Root__name__events.append('first')
        astichi_hole(slot__iter_1)

        @astichi_insert(slot__iter_1, order=1, ref=Pipeline.Root.Loop.Step1[1])
        def __astichi_contrib__Pipeline__slot__iter_1__0__Step1():
            astichi_import(events, outer_bind=True)
            events.append('second')
        astichi_hole(slot__iter_2)

        @astichi_insert(slot__iter_2, order=2, ref=Pipeline.Root.Loop.Step2[2])
        def __astichi_contrib__Pipeline__slot__iter_2__0__Step2():
            events = astichi_pass(events, outer_bind=True)
            events.append('third')
    result = events
    astichi_keep(__astichi_assign__inst__Pipeline__ref__Root__name__events)
    astichi_export(__astichi_assign__inst__Pipeline__ref__Root__name__events)
    __astichi_assign__inst__Pipeline__ref__Root__name__events = events
# astichi-provenance: eNrtWUtvI0UQnsSPPJwHAcUrwi4KC3izWjYkQQghpEVRFoSUYMHmvGqN7XZ67Mn0aB55HJC4AHvoA9IOAnHgJ/APuHHOb+C6XDlyoXqmx54Z9zhtJxv5gKXIme6q6q6qr75q93xb+umP21r4YQXd9QJW/pK2fBMHz4N6/fvgSfBNsMGKDdo6D54GG0Rjxc/ObIfPficmSye66eOAT+3pphkq1n+INdu+1Qzn6vpx2ui00QrYAqxpNImBCIU1WaHpnYXSB1RvgfR9LspWUCzlOk3UNrjk2hE1W/z5fd9yqGki0/Cwo5ub9nngNljZNCxs0WB/ms03qYlou+1iL9jX2Dy2Wqg/u8QfkxIVsk7e8husqDtHLvhMVntbJq+zNdTbi0Oph9BXho25NYQC8ga5E26YW3Ab5O7+NHl7XyPvwPe7sV2dzXbx+Sl1WqFxqUzOqMYqn0M0PYNaj3EborNRjz5eHGyLx5g8IDWQnYP9+8fY8lyJZMWmLrXM89jH2lNI/InuwHNQZ/Pd08Qkq3RPUQu3dd/0wudS9zSSm02Mwv7KEUDKu65rHFlpHMx4oIK9wYCW8Um4RwiexkqHHnVwnHdpGMsijGQxhIkBkE0hFUfbkediLh1RtuCd2xiyf8zjFNRz4j4XQx3WXO77RF5LeULWBtcsCGsFsLYgrNUyESBlud6i0FuJHd4M4ZI0+WoPLrLR7UzSyYes1kdvk1qeYzQQehLCmBc4QlsIHVBqAx7IR1ntTyKYkEd18il87cLfXp087mdeLUxsKd6BcWxTx7ukapbyova1XG9Z6K0mo6axGVFzKawUOIrZPPWBOFDDsFpBCKrZPWq5nm6lgEUWn7Fil8vEKLkrVqqlavZWelTPuHNPWuD3rgy0IlgrgrUiWHslJ2RswTV5qjlPoq1AbmRFGFlNoy5pv9rzQTYqQd0HEtT1aTO5qRCBhx62t14mBMmz8TDHPu47ooccB/sGqCS9cXA7LilOxgj16U0Vrc/7S/7MSg3qR8D8NYlF8luWrKoDqKoOwq8qhV/1UvhBN9n1eOKgVFK8DpKpyF4M58Byr7eCNeg4um1j7t1QpcVEOpJBYKW24QD9R7HgGktCYzWfMqtSyhSjmC21cJM6OnQhOCKAbdBXojLLxVIqk1XIAJX9rqQnAUcB0BZx1tyh33CbjmF72fT8pfyUcm02hrTEqSkRuSnYnCacesGKHPXq0lGfUZQuCU5QEWcl1zSaOI0VmAxRIjOvlLTMaFRasiyxGQd7vmO50ChQnVXCE4YNJ6tjcd6TWb9B4t+eROLf7hH/9iQS/0iHjWSFkl/yiftGzw/5lS7zTULZ5AX5e0yaLrvAqZzlB3i6ms/Tt6Q8LUYx+WcoMZN/x2PizqMpTVMn441Mq4bzJXayrRqoJvRbvZCSRjuzfEeLnXn4ugZa76xJHZSSbufOCLLr6rIRmW+rkXmnxg3L4nl9TI5zUtx5jwcdSLzzEP6ZBO7emUTu3ulx98543P1FImgHMuY9VLoNGHJO610y2XBsv+RqYHXEHlAVerfH6QH3hfLDFK2/mR7VMzvcFMIo+xNgc6LbQMkjhtO6ztP6y+oCf16hC3R+DAk7TVnT/7cASQvYGbsFTE9WCxgHiLILO9WbwYzeIOUIyFwVE7I95mFCLruuLJsZjVhP5qwkJTJ7w5oKKzvY9c3wx+rhIFo0kd1Eb7mMKYuCnrnacpKek/aWRzow9JtWF2Nb7d3CIIIu1N5JCOpVfxUx6l0vPlO4671xL4aePC6Gnzwq6uiQLY1yXjaMwyVKMXwwQgxlXKLAF8qB13OGJbUtC5F4bWMcWRQKOXz3tPkfTN1ODQ==
