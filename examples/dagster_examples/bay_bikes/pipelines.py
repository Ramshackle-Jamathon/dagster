from dagster import ModeDefinition, PresetDefinition, file_relative_path, pipeline

from .resources import local_transporter, mount, production_transporter, temporary_directory_mount
from .solids import (
    consolidate_csv_files,
    download_weather_report,
    download_zipfiles_from_urls,
    unzip_files,
    upload_file_to_bucket,
)

local_mode = ModeDefinition(
    name='local',
    resource_defs={'transporter': local_transporter, 'volume': temporary_directory_mount},
)


production_mode = ModeDefinition(
    name='production', resource_defs={'transporter': production_transporter, 'volume': mount}
)


@pipeline(
    mode_defs=[local_mode, production_mode],
    preset_defs=[
        PresetDefinition.from_files(
            'dev',
            mode='local',
            environment_files=[
                file_relative_path(__file__, 'environments/base.yaml'),
                file_relative_path(__file__, 'environments/dev.yaml'),
            ],
        ),
        PresetDefinition.from_files(
            'production',
            mode='production',
            environment_files=[
                file_relative_path(__file__, 'environments/base.yaml'),
                file_relative_path(__file__, 'environments/production.yaml'),
            ],
        ),
    ],
)
def extract_monthly_bay_bike_pipeline():
    upload_consolidated_csv = upload_file_to_bucket.alias('upload_consolidated_csv')
    upload_consolidated_csv(consolidate_csv_files(unzip_files(download_zipfiles_from_urls())))


@pipeline(
    mode_defs=[local_mode, production_mode],
    preset_defs=[
        PresetDefinition.from_files(
            'def',
            environment_files=[
                file_relative_path(__file__, 'environments/base.yaml')
            ]
        )
    ]
)
def extract_daily_weather_data_pipeline():
    upload_weather_report = upload_file_to_bucket.alias('upload_weather_report')
    upload_weather_report(download_weather_report())
