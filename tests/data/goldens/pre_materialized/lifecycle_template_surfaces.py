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
