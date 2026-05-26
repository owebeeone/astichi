astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    astichi_pyimport(module=types, names=(SimpleNamespace,))
    astichi_comment('lifecycle template module')

    class ExampleState:
        __slots__ = (*astichi_insert(state_slots, '_count_current'), *astichi_insert(state_slots, '_label_value'))

        def __init__(self, state_params__astichi_param_hole__):
            astichi_hole(state_init_body)

            @astichi_insert(state_init_body, ref=Root.StateInitBody)
            def __astichi_contrib__Root__state_init_body__0__StateInitBody():
                astichi_comment('state field initialization')
                astichi_import(self)
                self.astichi_ref('_count_current')._ = astichi_pass(count, outer_bind=True)
                self.astichi_ref('_label_value')._ = astichi_pass(label, outer_bind=True)

        @astichi_insert(state_params, kind='params', ref=StateParams)
        def __astichi_param_contrib__Root__state_params__0__StateParams(*, count: astichi_ref('int')=0, label: astichi_ref('str')='x'):
            pass

    class Example(*astichi_insert(class_bases, object)):
        __slots__ = ('_state',)

        def __init__(self, facade_params__astichi_param_hole__):
            self._state = ExampleState(astichi_hole(state_ctor_args), astichi_insert(state_ctor_args, astichi_funcargs(count=astichi_pass(count, outer_bind=True), label=astichi_pass(label, outer_bind=True))))

        @astichi_insert(facade_params, kind='params', ref=FacadeParams)
        def __astichi_param_contrib__Root__facade_params__0__FacadeParams(*, count: astichi_ref('int')=0, label: astichi_ref('str')='x'):
            pass
        astichi_hole(properties)

        @astichi_insert(properties, ref=Root.CountProperty)
        def __astichi_contrib__Root__properties__0__CountProperty():
            astichi_comment('count property template')

            @property
            def count(self):
                return self._state.astichi_ref('_count_current')

            @count.setter
            def count(self, value):
                self._state.astichi_ref('_count_current')._ = value

        @astichi_insert(properties, order=1, ref=Root.LabelProperty)
        def __astichi_contrib__Root__properties__1__LabelProperty():
            astichi_comment('label property template')

            @property
            def label(self):
                return self._state.astichi_ref('_label_value')
    result = Example(count=1, label='alpha')
    result.count = 2
    summary = SimpleNamespace(count=result.count, label=result.label, class_name=type(result).__name__)
# astichi-provenance: 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
