import uuid

import pytest

from dagster import (
    ConfigField,
    ExecutionContext,
    Field,
    OutputDefinition,
    PipelineDefinition,
    PipelineContextDefinition,
    config,
    execute_pipeline,
    lambda_solid,
    solid,
    types,
)
from dagster.core.errors import (DagsterTypeError, DagsterInvariantViolationError)
from dagster.utils.logging import INFO

# protected variable. need to test loggers
# pylint: disable=W0212


def test_default_context():
    called = {}

    @solid(inputs=[], outputs=[OutputDefinition()])
    def default_context_transform(info):
        called['yes'] = True
        for logger in info.context._logger.loggers:
            assert logger.level == INFO

    pipeline = PipelineDefinition(solids=[default_context_transform])
    execute_pipeline(pipeline)

    assert called['yes']


def test_run_id():
    called = {}

    def construct_context(info):
        called['yes'] = True
        assert uuid.UUID(info.run_id)
        return ExecutionContext()

    pipeline = PipelineDefinition(
        solids=[],
        context_definitions={'default': PipelineContextDefinition(context_fn=construct_context, )}
    )
    execute_pipeline(pipeline)

    assert called['yes']


def test_default_context_with_log_level():
    @solid(inputs=[], outputs=[OutputDefinition()])
    def default_context_transform(info):
        for logger in info.context._logger.loggers:
            assert logger.level == INFO

    pipeline = PipelineDefinition(solids=[default_context_transform])
    execute_pipeline(
        pipeline,
        environment=config.Environment(context=config.Context(config={'log_level': 'INFO'}))
    )

    with pytest.raises(DagsterTypeError, message='Argument mismatch in context default'):
        execute_pipeline(
            pipeline,
            environment=config.Environment(context=config.Context(config={'log_level': 2}))
        )


def test_default_value():
    def _get_config_test_solid(config_key, config_value):
        @solid(inputs=[], outputs=[OutputDefinition()])
        def config_test(info):
            assert info.context.resources == {config_key: config_value}

        return config_test

    pipeline = PipelineDefinition(
        solids=[_get_config_test_solid('field_one', 'heyo')],
        context_definitions={
            'custom_one':
            PipelineContextDefinition(
                config_field=ConfigField.config_dict_field(
                    'CustomOneDict',
                    {
                        'field_one':
                        Field(
                            dagster_type=types.String,
                            is_optional=True,
                            default_value='heyo',
                        ),
                    },
                ),
                context_fn=lambda info: ExecutionContext(resources=info.config),
            ),
        }
    )

    execute_pipeline(
        pipeline, environment=config.Environment(context=config.Context('custom_one', {}))
    )


def test_custom_contexts():
    @solid(inputs=[], outputs=[OutputDefinition()])
    def custom_context_transform(info):
        assert info.context.resources == {'field_one': 'value_two'}

    pipeline = PipelineDefinition(
        solids=[custom_context_transform],
        context_definitions={
            'custom_one':
            PipelineContextDefinition(
                config_field=ConfigField.config_dict_field(
                    'CustomOneDict',
                    {'field_one': Field(dagster_type=types.String)},
                ),
                context_fn=lambda info: ExecutionContext(resources=info.config),
            ),
            'custom_two':
            PipelineContextDefinition(
                config_field=ConfigField.config_dict_field(
                    'CustomTwoDict',
                    {'field_one': Field(dagster_type=types.String)},
                ),
                context_fn=lambda info: ExecutionContext(resources=info.config),
            )
        },
    )

    environment_one = config.Environment(
        context=config.Context('custom_one', {'field_one': 'value_two'})
    )

    execute_pipeline(pipeline, environment=environment_one)

    environment_two = config.Environment(
        context=config.Context('custom_two', {'field_one': 'value_two'})
    )

    execute_pipeline(pipeline, environment=environment_two)


def test_yield_context():
    events = []

    @solid(inputs=[], outputs=[OutputDefinition()])
    def custom_context_transform(info):
        assert info.context.resources == {'field_one': 'value_two'}
        assert info.context._context_stack['foo'] == 'bar'  # pylint: disable=W0212
        events.append('during')

    def _yield_context(info):
        events.append('before')
        context_stack = {'foo': 'bar'}
        context = ExecutionContext(resources=info.config, context_stack=context_stack)
        yield context
        events.append('after')

    pipeline = PipelineDefinition(
        solids=[custom_context_transform],
        context_definitions={
            'custom_one':
            PipelineContextDefinition(
                config_field=ConfigField.config_dict_field(
                    'CustomOneDict', {'field_one': Field(dagster_type=types.String)}
                ),
                context_fn=_yield_context,
            ),
        }
    )

    environment_one = {
        'context': {
            'custom_one': {
                'config': {
                    'field_one': 'value_two',
                },
            },
        },
    }

    execute_pipeline(pipeline, environment=environment_one)

    assert events == ['before', 'during', 'after']


# TODO: reenable pending the ability to specific optional arguments
# https://github.com/dagster-io/dagster/issues/56
def test_invalid_context():
    @lambda_solid
    def never_transform():
        raise Exception('should never execute')

    default_context_pipeline = PipelineDefinition(solids=[never_transform])

    environment_context_not_found = config.Environment(context=config.Context('not_found', {}))

    with pytest.raises(DagsterTypeError, message='Context not_found does not exist'):
        execute_pipeline(
            default_context_pipeline,
            environment=environment_context_not_found,
            throw_on_error=True
        )

    environment_field_name_mismatch = config.Environment(
        context=config.Context(config={'unexpected': 'value'})
    )

    with pytest.raises(DagsterTypeError, message='Argument mismatch in context default'):
        execute_pipeline(
            default_context_pipeline,
            environment=environment_field_name_mismatch,
            throw_on_error=True
        )

    with_argful_context_pipeline = PipelineDefinition(
        solids=[never_transform],
        context_definitions={
            'default':
            PipelineContextDefinition(
                config_field=ConfigField.config_dict_field(
                    'SingleStringDict', {'string_field': Field(types.String)}
                ),
                context_fn=lambda info: info.config,
            )
        }
    )

    environment_no_config_error = config.Environment(context=config.Context(config={}))

    with pytest.raises(DagsterTypeError, message='Argument mismatch in context default'):
        execute_pipeline(
            with_argful_context_pipeline,
            environment=environment_no_config_error,
            throw_on_error=True
        )

    environment_type_mismatch_error = config.Environment(
        context=config.Context(config={'string_field': 1})
    )

    with pytest.raises(DagsterTypeError, message='Argument mismatch in context default'):
        execute_pipeline(
            with_argful_context_pipeline,
            environment=environment_type_mismatch_error,
            throw_on_error=True
        )
