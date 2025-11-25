"""Generation of content fixtures"""

import hashlib
import json
import random

from testdata_factory.models import (
    ContentStyle,
    DataBatch,
    FactoryConfig,
    GeneratedRecord,
    RecordMetadata,
)


class TestDataGenerator:
    """Generate fixtures from a validated scenario config"""

    def generate(self, config: FactoryConfig) -> DataBatch:
        rng = random.Random(config.generation.seed)
        template = config.template
        identity_source = {
            "scenario": config.scenario,
            "seed": config.generation.seed,
            "template": template.model_dump(mode="json"),
        }
        canonical_identity = json.dumps(
            identity_source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        identity_fingerprint = hashlib.sha256(canonical_identity).hexdigest()[:12]
        records: list[GeneratedRecord] = []

        for sequence in range(1, config.generation.count + 1):
            style = rng.choice(template.styles)
            records.append(
                GeneratedRecord(
                    external_id=(
                        f"{template.id_prefix}-{identity_fingerprint}-"
                        f"{config.generation.seed}-{sequence:04d}"
                    ),
                    title=rng.choice(template.titles),
                    body=rng.choice(template.bodies),
                    style=ContentStyle.model_validate(style.model_dump()),
                    metadata=RecordMetadata(
                        scenario=config.scenario,
                        seed=config.generation.seed,
                        sequence=sequence,
                    ),
                )
            )

        return DataBatch(
            scenario=config.scenario,
            seed=config.generation.seed,
            items=records,
        )
