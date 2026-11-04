"""从已下载的固定官方配置生成无豁免规则；不在 CI 联网解析规则。"""

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA256 = "e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf"
P3_DOCUMENT_DIGEST = "a469bb6825770325a664b4770b0f17c78786ecec2126142870e1bd7dd08a6245"
P3_PUBLIC_ROW = '  "' + "open" + 'api_sha256": "' + P3_DOCUMENT_DIGEST + '",'
P3_PUBLIC_PATH = r"(?:^|/)docs/contracts/p3-checks\.json$"
P3_ROW_DIGEST = "4405db53329b7d9b9fb9d5ff920a1e9221dd3ecc57202de57bf838325a03f901"
B_PUBLIC_ROW = '    "' + "sec" + 'rets": "dir/index/fullreachablegit 0 before final stage"'
B_PUBLIC_PATH = r"(?:^|/)frontend/evidence/b02-read/validation\.json$"
B_ROW_DIGEST = "2fd5c5a9ece651f39320ee19c19b067b6f388064fd47cc64bdd2c6dc78f53437"

RO_PUBLIC_ROW = (
    '                ["explicit_ro_'
    + 'recheck_authorized", "explicit_ro_'
    + 'recheck_dispatched"],'
)
RO_PUBLIC_PATH = r"(?:^|/)scripts/p4_acceptance\.py$"
RO_ROW_DIGEST = "07e3542d6dbdbc59bbd099207f38277800daec3217315d0f5dde8549e6df32d5"
RO_SOURCE_COMMIT = "348a9f4ca0c4159d9b3a2cbdf0921623e5bb5600"


WOO_SOURCE_COMMIT = "bbb507b08f1a937f3466369044db27054dee2879"
WOO_SEED_ROW = (
    "            'meta_"
    + "key' => '_commerceops_lab_"
    + "key', 'meta_value' => $key, 'fields' => 'ids']);"
)
WOO_FIXTURE_ROW = '      "' + "key" + '": "' + "partial_" + 'refund",'
WOO_PUBLIC_EXCEPTIONS = (
    (
        "infrastructure/woo-lab/seed.php",
        r"(?:^|/)infrastructure/woo-lab/seed\.php$",
        WOO_SEED_ROW,
        "66b247190dfa6c8e39e40251c2166858090553e24c393565b3c3807d10119527",
        25,
    ),
    (
        "tests/fixtures/woocommerce-local/seed.json",
        r"(?:^|/)tests/fixtures/woocommerce-local/seed\.json$",
        WOO_FIXTURE_ROW,
        "4eccbfac014eeaff0495d26b0ce2073de68aab89987717bb70b6004647b686f4",
        169,
    ),
)

M2_SOURCE_COMMIT = "85f477c46d5348a9e3667f606d273eff3cbaaa32"
M2_PUBLIC_EXCEPTIONS = (
    (
        "frontend/tooling/sync-p5-schema.mjs",
        r"(?:^|/)frontend/tooling/sync-p5-schema\.mjs$",
        "a3bcd562c3b2193866f90fe3efe03523c2f2ce303370fb1fe9f51cdcb1d57408",
        5,
    ),
    (
        "tests/e2e/web/phase5/creation-ui.spec.ts",
        r"(?:^|/)tests/e2e/web/phase5/creation-ui\.spec\.ts$",
        "d5e9e9954765601d77bfdf3e42286cabfdf39c8f7501c3c3c57142277accf0b6",
        153,
    ),
)


M2_CONSUMER_SOURCE_COMMIT = "27af9c359c35b1f48f2530681a2d400910914d28"
M2_CONSUMER_EXCEPTIONS = (
    (
        "tests/e2e/web/contracts/m2-consumer.spec.ts",
        "(?:^|/)tests/e2e/web/contracts/m2-consumer\\.spec\\.ts$",
        "708e007826382db1ba2e2d2890c189bf0a8b071096ecf13049b517152c52f22e",
        39,
    ),
    (
        "tests/e2e/web/contracts/m2-consumer.spec.ts",
        "(?:^|/)tests/e2e/web/contracts/m2-consumer\\.spec\\.ts$",
        "503a15a10a4d484e96b74719fad06cf375a7a48a1a2b54c827dcbdc9acdb85c5",
        40,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "7eba5a3c9dd2d0c4203ab7e5470ef45a8c35d46e1af70e79836278617c849e01",
        58,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "015f7c967bfa67d3dcf5171a1be76083ee509fa7a280e41ca52200b33a31e580",
        75,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "34cf7ac263107a4d2be2015a0f264a6d1e4c315d8f58d2fbe345d74c1795a0e7",
        257,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "f0c3acd784b36b1f3472875fc9c765e587424d9237562f34b7b937da5b8bfda0",
        277,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "d503b52d88c272a7c9b8f26edb249f4e34adf47f08b3bf17c7ae8faa288246a5",
        291,
    ),
    (
        "tests/e2e/web/live/m2-consumer.ts",
        "(?:^|/)tests/e2e/web/live/m2-consumer\\.ts$",
        "dbbec2bf789237600d1426e7c9968c147cd1ef753e0fc753b689e199667937d7",
        439,
    ),
)


# M3: immutable public code rows; candidate requires independent review before integration.
M3_PUBLIC_EXCEPTIONS = (
    (
        "b63f9bc5efc9b360c872df4ef15481ba15420503",
        "frontend/m3-tests/daily-read.fixture.json",
        "^frontend/m3\\-tests/daily\\-read\\.fixture\\.json$",
        "9ba1d2eaf28dee54c74df8009dfe068f2205261d884e6eee9b5b816c0dfde3d8",
        137,
    ),
    (
        "b63f9bc5efc9b360c872df4ef15481ba15420503",
        "frontend/lib/m3-read-client.ts",
        "^frontend/lib/m3\\-read\\-client\\.ts$",
        "7cd875fcc4788e55e5bd0ecb98a6f6a096fa1d4539bad46c62633047ef543c41",
        72,
    ),
    (
        "b4b3c9ea8ab4b60c3406178c7a08e4ca6d3fb9e4",
        "frontend/m3-tests/daily-empty.fixture.json",
        "^frontend/m3\\-tests/daily\\-empty\\.fixture\\.json$",
        "9ba1d2eaf28dee54c74df8009dfe068f2205261d884e6eee9b5b816c0dfde3d8",
        140,
    ),
    (
        "e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8",
        "backend/src/commerceops/infrastructure/knowledge_copy_repository.py",
        "^backend/src/commerceops/infrastructure/knowledge_copy_repository\\.py$",
        "f88e20474894ad7b68ada1bb12c042aa419747488fdb40bcba47523e5503cd26",
        271,
    ),
    (
        "e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8",
        "backend/migrations/versions/0020_p6_knowledge_copy.py",
        "^backend/migrations/versions/0020_p6_knowledge_copy\\.py$",
        "2016dfbb0029ad7285c16c3169cb895854864410744d51bb89fc5d6592fd7948",
        152,
    ),
    (
        "8a6c6ebb59abf451c810bb6aebcdf1b8f6510e9d",
        "backend/migrations/versions/0020_p6_knowledge_copy.py",
        "^backend/migrations/versions/0020_p6_knowledge_copy\\.py$",
        "1e860e56789ea17cf4df6d514d07d28135dd78010d9e9230cc6f1cc2f48464e0",
        54,
    ),
    (
        "22b60150add80f59613445260e1e2851b5d0b86f",
        "backend/src/commerceops/application/commerce/readonly_inquiry_tools.py",
        "^backend/src/commerceops/application/commerce/readonly_inquiry_tools\\.py$",
        "23006e136c68711f9ce3672034e86c0176d21387c04c9824468927b5be39d942",
        199,
    ),
    (
        "1a78d5a23fd888265cc8e30dde6c492d8b6c94cc",
        "backend/src/commerceops/entrypoints/inquiry_http.py",
        "^backend/src/commerceops/entrypoints/inquiry_http\\.py$",
        "eaf8d3d2af552e3a55b0f9c3a45ba8dcaf93438deda500af53d3792fcae842cf",
        176,
    ),
    (
        "e2e50f53661a8b07e8bf62f1ad4afa6fe5c769da",
        "backend/migrations/versions/0021_p6_readonly_inquiries.py",
        "^backend/migrations/versions/0021_p6_readonly_inquiries\\.py$",
        "47034fc2724e57435d98f01be94605e95af668f2f3c865c1bed96b5b9a0e401a",
        80,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "backend/src/commerceops/entrypoints/knowledge_copy_http.py",
        "^backend/src/commerceops/entrypoints/knowledge_copy_http\\.py$",
        "e03dae298ac58f76d1e2323a5983ffafe10c5062e0dc6e1c52aacd26f38427bc",
        218,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "backend/src/commerceops/entrypoints/knowledge_copy_http.py",
        "^backend/src/commerceops/entrypoints/knowledge_copy_http\\.py$",
        "c4c65eb64554649746e6cd17210ab907d2b3613af434dc3bf30e68161b0d8d91",
        229,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "frontend/lib/p6-inquiry-client.ts",
        "^frontend/lib/p6\\-inquiry\\-client\\.ts$",
        "32d3ade5904ace51ba00499406316ec09cca2c53103c6f32b3817065ed665181",
        123,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "frontend/lib/p6-copy-client.ts",
        "^frontend/lib/p6\\-copy\\-client\\.ts$",
        "32cf2c9499c2b9f86c23973c9dd6794693eb20408577d687c531a0af19bd5fc3",
        46,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "frontend/tooling/check-p6-daily-s3-schema.mjs",
        "^frontend/tooling/check\\-p6\\-daily\\-s3\\-schema\\.mjs$",
        "879663a25802cf1a8ea527dc2b34b5ac0948ca2fd4c620be60f57124bebe9478",
        5,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "frontend/m3-tests/daily-s3.fixture.json",
        "^frontend/m3\\-tests/daily\\-s3\\.fixture\\.json$",
        "9761f2d4abc97c05a69bdd1c48a5e9ec572973bc8d347a90f0163dd4aebe7dd2",
        72,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "frontend/m3-tests/daily-s3.fixture.json",
        "^frontend/m3\\-tests/daily\\-s3\\.fixture\\.json$",
        "9761f2d4abc97c05a69bdd1c48a5e9ec572973bc8d347a90f0163dd4aebe7dd2",
        169,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_m3_local_runtime.py",
        "^tests/test_m3_local_runtime\\.py$",
        "1560f72d6e586424aa2a01bccb1c4de0a4aadbe00a4740c4b55c8b1d2f2e2a68",
        191,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_m3_inquiry_wiring.py",
        "^tests/test_m3_inquiry_wiring\\.py$",
        "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        102,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_p6_inquiry_pg.py",
        "^tests/test_p6_inquiry_pg\\.py$",
        "01877a828b93d29e948eebd5a18fbd1219da0791cc0e12ddc9a873167fa6e47b",
        602,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_p6_copy_pg.py",
        "^tests/test_p6_copy_pg\\.py$",
        "ce347dbf648728b418aa6fa7e32c357927ff5b865a06507e9bdfe4363a80c2ab",
        172,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_p6_copy_pg.py",
        "^tests/test_p6_copy_pg\\.py$",
        "acc74328a284ec6eead7a636ebb20716c2048dbd7f8e05d8df40934c7245ffca",
        348,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_p6_copy_pg.py",
        "^tests/test_p6_copy_pg\\.py$",
        "ce347dbf648728b418aa6fa7e32c357927ff5b865a06507e9bdfe4363a80c2ab",
        354,
    ),
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "tests/test_p6_copy_pg.py",
        "^tests/test_p6_copy_pg\\.py$",
        "acc74328a284ec6eead7a636ebb20716c2048dbd7f8e05d8df40934c7245ffca",
        369,
    ),
    (
        "f20dadf10511116e5d67ecc6f841d1e375009a1e",
        "tests/test_m3_copy_app_pg.py",
        "^tests/test_m3_copy_app_pg\\.py$",
        "9fe7174fdb0526dcf7548af9e7f992bd4cd6da2d2969025200412fc5c748ecc7",
        31,
    ),
    (
        "08d8b8c6e95fd1bd55bdee8574a554fb363b6f31",
        "tests/test_pg_owned_subnet.py",
        "^tests/test_pg_owned_subnet\\.py$",
        "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        113,
    ),
)

M3_HISTORY_PUBLIC_EXCEPTIONS = (
    (
        "4c6d601b9b5b54010e6004993bd710613fdf9a3a",
        "tests/test_m3_copy_app_pg.py",
        "^tests/test_m3_copy_app_pg\\.py$",
        "1782394b2da3adb48a0fdcfd478ea67663d4f7d02e90cac840fb061576347b49",
        27,
    ),
    (
        "ba5c550d56ccb9c3ff141018a96719316787857e",
        "frontend/tooling/check-p6-daily-s3-schema.mjs",
        "^frontend/tooling/check\\-p6\\-daily\\-s3\\-schema\\.mjs$",
        "ff43a3b2ff169e391094eb4d00854cfdfa6b4b367666ae6761dc9eb9c3ec3037",
        5,
    ),
)


M3_SPAN_PUBLIC_EXCEPTIONS = (
    (
        "ac6edf24515aa2148037aa24a84d0618f1e30f74",
        "backend/migrations/versions/0023_p6_copy_drafts.py",
        "^backend/migrations/versions/0023_p6_copy_drafts\\.py$",
        "96ce803f7ab588bddd5838a711219fab5becdb93daac2cf3803dcf0f99b5b510",
        34,
        35,
    ),
)


V4_SOURCE_COMMIT = "fa96764cf2b8e3ab9adbb579b764f600a7d17e60"
V4_PUBLIC_EXCEPTIONS = (
    (
        "docs/v4/baseline/API_EVENTS_CONTRACT.md",
        "528898a328812d86eb33d61c91e19abeded3af2a10f3f704e8a08e4ed37bca2d",
        14,
        14,
        "9c3ca0a9c8ed46b0201fc53f4c8914e194f2e81655f7a1938d6c4733ff6faddf",
        33,
        66,
    ),
    (
        "docs/v4/baseline/evidence/A_EXECUTION_RECEIPT.json",
        "56ac6716fc7063f773d8f0bdfa2c06e127018b85e8145add1b2f96ec05825be0",
        5,
        6,
        "83ecc9e7036a080f5530ff0dac847b357765fa83645a244c07ea5be9933320d3",
        59,
        27,
    ),
    (
        "docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json",
        "856cb9d6ff038755db512d1f403343e4edd2582bd34d31327e83a34bf8f30830",
        5,
        5,
        "4215f99f741938888312b0a55a895ca8aee5a68f77cd084d675590f92ef4f5c0",
        5,
        95,
    ),
    (
        "docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json",
        "73132a728480edc215e784b5a744c975d92faa6d5fc8b59dc3f08f7774b712b2",
        9,
        9,
        "f567aa1e427a8fbccb4d9626c06aea3b8d039499925aac1e0d14e57d01b6c872",
        5,
        95,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        42,
        42,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        64,
        64,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        86,
        86,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        108,
        108,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        130,
        130,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020",
        152,
        152,
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
        9,
        55,
    ),
    (
        "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "d85fa80d9bbc30593eca344f3779926519709f713c5fec429acde709c30ac6aa",
        18512,
        18512,
        "b8653d0c62cca5e6f2108b44e9c6b9982a15cef79e8bfc2cf01b9509afc03ebb",
        17,
        57,
    ),
    (
        "docs/v4/baseline/v4-public-openapi.json",
        "8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87",
        99,
        99,
        "2207071b3e12e69394e74480112e69daef3b21c0fd8baaa66abb4a584b7f39d6",
        11,
        74,
    ),
    (
        "docs/v4/baseline/v4-public-openapi.json",
        "8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87",
        251,
        251,
        "2207071b3e12e69394e74480112e69daef3b21c0fd8baaa66abb4a584b7f39d6",
        11,
        74,
    ),
)


V4_ADDITIONAL_HISTORY = (
    (
        "c5f4d101339fed02c463c6dc8058bb92b15881ca",
        "frontend/components/v4/demo.tsx",
        7,
        7,
        8,
        42,
        "321c40305b3977373aa33cad247d66eccb91a9af3b6d5ef861d390d49d221456",
        "323916e3773577c1a0819f53f4623f1e8c4f08d02814314c52f26a1291d6979d",
    ),
    (
        "c5f4d101339fed02c463c6dc8058bb92b15881ca",
        "frontend/components/v4/demo.tsx",
        10,
        10,
        166,
        203,
        "717bd4cc248808ee824f89a7f1ee644900867102a54b02047a819e046f802327",
        "5f0689911c62ddd1332b2e427ce3121ad275e7d073946f672bae83c9b0d8dc3f",
    ),
    (
        "75dc6d55e386d85713943df0fb7a0b3ba5fef053",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        3,
        3,
        5,
        44,
        "b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a",
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
    ),
    (
        "75dc6d55e386d85713943df0fb7a0b3ba5fef053",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        16,
        16,
        7,
        46,
        "6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6",
        "2cdb26c38d3fed7008faac0d3db964536d381dfeee2bfbdfbac31c17575c743e",
    ),
    (
        "772f95927546dc3c648b58cd3906f91cae64c2f4",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        3,
        3,
        5,
        44,
        "b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a",
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
    ),
    (
        "772f95927546dc3c648b58cd3906f91cae64c2f4",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        16,
        16,
        7,
        46,
        "6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6",
        "2cdb26c38d3fed7008faac0d3db964536d381dfeee2bfbdfbac31c17575c743e",
    ),
    (
        "46e44e5548d720bdb735e2a0f4673bdc73854de4",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        3,
        3,
        5,
        44,
        "b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a",
        "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
    ),
    (
        "46e44e5548d720bdb735e2a0f4673bdc73854de4",
        "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        16,
        16,
        7,
        46,
        "6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6",
        "2cdb26c38d3fed7008faac0d3db964536d381dfeee2bfbdfbac31c17575c743e",
    ),
    (
        "48c30d224529319d5a9ff203429eeff86060fc00",
        "frontend/lib/v4-openapi.json",
        99,
        99,
        11,
        74,
        "8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87",
        "2207071b3e12e69394e74480112e69daef3b21c0fd8baaa66abb4a584b7f39d6",
    ),
    (
        "48c30d224529319d5a9ff203429eeff86060fc00",
        "frontend/lib/v4-openapi.json",
        251,
        251,
        11,
        74,
        "8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87",
        "2207071b3e12e69394e74480112e69daef3b21c0fd8baaa66abb4a584b7f39d6",
    ),
)


def v4_additional_history_findings() -> list[dict[str, object]]:
    """Ten separately authorized historical public metadata/UI/schema findings only."""
    return [
        {
            "rule": "generic-api-key",
            "path": path,
            "source_commit": commit,
            "reported_line": line,
            "end_line": end,
            "start_column": col,
            "end_column": end_col,
            "exact_span_sha256": digest,
            "match_sha256": match_digest,
            "fingerprint": f"{commit}:{path}:generic-api-key:{line}",
        }
        for commit, path, line, end, col, end_col, digest, match_digest in V4_ADDITIONAL_HISTORY
    ]


V4_PREFLIGHT_SNAPSHOTS: tuple[dict[str, Any], ...] = (
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "1c1525088708e12b552973ba9d0ab1b7cd6f1ec6",
        "reported_line": 154,
        "end_line": 154,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "1c1525088708e12b552973ba9d0ab1b7cd6f1ec6",
        "reported_line": 266,
        "end_line": 266,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "1c1525088708e12b552973ba9d0ab1b7cd6f1ec6",
        "reported_line": 371,
        "end_line": 371,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "1c1525088708e12b552973ba9d0ab1b7cd6f1ec6",
        "reported_line": 401,
        "end_line": 401,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 118,
        "end_line": 119,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 220,
        "end_line": 220,
        "start_column": 39,
        "end_column": 68,
        "exact_span_sha256": "717aecdd18fac4e6cc7b9a057f6cf59741beb662440a475f267c9cdabe243e8c",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 222,
        "end_line": 222,
        "start_column": 30,
        "end_column": 59,
        "exact_span_sha256": "04a90c4bd9c229c2d68c406fa4d367e18912ab5a1e357e9526792100866429ae",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 351,
        "end_line": 351,
        "start_column": 11,
        "end_column": 40,
        "exact_span_sha256": "0385f1ec491185e384352946f893e8aed2373023b7ac5c2967d1da50068d1273",
        "match_sha256": "7ef80a218c721c53c39c59797ac234908fa362326c3a16bd27212f39ed9cd066",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 367,
        "end_line": 367,
        "start_column": 45,
        "end_column": 81,
        "exact_span_sha256": "b40316de11ee2760c5bca9ed70dfdf7885f89ec90d8db77d8e4d76fdc3bd3987",
        "match_sha256": "9f8edb26e9baf5474a20e14ef0c07ec90391dd1fde8c79ac7648657a16ff3b53",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 385,
        "end_line": 385,
        "start_column": 10,
        "end_column": 47,
        "exact_span_sha256": "0f62de7a54e402563bc2e792481dc68b87b6b034d6cf6d9175d5f508b4d9c967",
        "match_sha256": "044857216fb64994e9715a78b57820aafdcf054dd888c32d8e61717377cb507a",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 406,
        "end_line": 406,
        "start_column": 46,
        "end_column": 82,
        "exact_span_sha256": "f14569df8150ea3f77d091db08ed46777d518c2cb3eb7ca7ed14861bcec3a7e3",
        "match_sha256": "28c024d9aec42b9c593d110365f31b8851854b35c35374d43707f8cc6cd8cec5",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 430,
        "end_line": 430,
        "start_column": 26,
        "end_column": 53,
        "exact_span_sha256": "0953ddca366332aa9054120e733607b99fefbbcff21e510141df6b51a46caf29",
        "match_sha256": "e1a66ed14209cdae0b093f121569e5183db9b5b3ed679fce0aa095d5b1b414a8",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/app/v4/[[...path]]/page.tsx",
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "reported_line": 9,
        "end_line": 9,
        "start_column": 43,
        "end_column": 116,
        "exact_span_sha256": "87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b",
        "match_sha256": "896d3957535652b65e2eb532731f764c8b1d7f6eafe0bbc90df606658c4b367b",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "reported_line": 77,
        "end_line": 77,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "10276796f6bda05e7e2bcdb7ba240bc70434b286e424249179685824a34a3363",
        "match_sha256": "94b393277ca683c9f02c382c5d8d91d0f2590c3d8463ea71c9932728cb3032a9",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "reported_line": 83,
        "end_line": 83,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e",
        "match_sha256": "1a6523207f88d27bc1cfa16d3b503fc70a8d08a458298f3c796b3f60afdc12cd",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "reported_line": 89,
        "end_line": 89,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e",
        "match_sha256": "1a6523207f88d27bc1cfa16d3b503fc70a8d08a458298f3c796b3f60afdc12cd",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "reported_line": 112,
        "end_line": 112,
        "start_column": 6,
        "end_column": 64,
        "exact_span_sha256": "a8b7d2dab131363a39ecd7bb344cb3be1b99800aff98441d94b6e669bb0ff97d",
        "match_sha256": "d71ece3ce74a7079b002e2b5941a7f883b1a1415e52237a96df11bf77ddfdd8e",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/src/commerceops/infrastructure/v4_demo_sessions.py",
        "source_commit": "d57808f0627821ab202e054e7d464fa2d4b9798c",
        "reported_line": 133,
        "end_line": 133,
        "start_column": 28,
        "end_column": 78,
        "exact_span_sha256": "6010903555ef6d9dd8a07f2798439009762f93c2694e7171a02fc6af17310616",
        "match_sha256": "847110db021532757d13f6e902f8a849f8ad9b4d188c633de6390f8b5e5b4fab",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/review/SCAN_a4f.md",
        "source_commit": "b726949b670153d9b5393225f890f0c919ee6ea5",
        "reported_line": 28,
        "end_line": 28,
        "start_column": 216,
        "end_column": 245,
        "exact_span_sha256": "5189f504e28b860e65ff5157f7e13fdeac74a5f2941df3ddf045bcb03e902730",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 155,
        "end_line": 155,
        "start_column": 20,
        "end_column": 50,
        "exact_span_sha256": "5ae7df16f7216f67ea2645dcef5730b23e9cf1d886985b1f58ecbd1fceb07259",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 174,
        "end_line": 174,
        "start_column": 49,
        "end_column": 70,
        "exact_span_sha256": "7293c9a4fd3f141f0a1aae4e56ff1e36c79a500a8541c0c7b65af6584d1ab0a1",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 201,
        "end_line": 201,
        "start_column": 51,
        "end_column": 72,
        "exact_span_sha256": "0b1c32a3a906b1cbb3e54b26c76eb430044e421008f76e9b6a2edea7d9836ffe",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/v4-tests/lifecycle.waiter.mjs",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 9,
        "end_line": 9,
        "start_column": 10,
        "end_column": 63,
        "exact_span_sha256": "c8b2b58b10acf12b247f59937a6fd4f4ee4170230d53b7dc806e0c41ce9f5cd6",
        "match_sha256": "0e979f26f5711d6c7674669d81cf34c804a8bc314f386508b229dc20989cd730",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_negatives.py",
        "source_commit": "9727cf15aba3d2b2fa27bba6b82682c403903187",
        "reported_line": 41,
        "end_line": 41,
        "start_column": 43,
        "end_column": 64,
        "exact_span_sha256": "9eae89315546427045520b575cb3ef7d7e6578ccdb9da58d34c78982841a8272",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_ttl_probe.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 137,
        "end_line": 137,
        "start_column": 5,
        "end_column": 50,
        "exact_span_sha256": "d9750ce8385dbb070189901b02ded4ed09d2f868244afdca4c8e8ce7dabac003",
        "match_sha256": "5e4ad6f415caa2abda096640ea1af5414dd9d0e6beb00eadb1bfc8da2b4811c0",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_driver.py",
        "source_commit": "1684e0455978b46ddad607e09d85a1af5657ab1a",
        "reported_line": 735,
        "end_line": 735,
        "start_column": 10,
        "end_column": 44,
        "exact_span_sha256": "257d31b06b9ca99bcf1d666842c5dd8771b960a3aec485e029f620614fe3b267",
        "match_sha256": "f5d8f078e1d354c22377e9c092e9cdde6d794776f5a9fdcb32257cae559f277f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "source_commit": "1684e0455978b46ddad607e09d85a1af5657ab1a",
        "reported_line": 19,
        "end_line": 19,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "cfdb4732beb794c9d3e5092094e8f7c7123b45e0ad9ad04dc387ee54008008c8",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "source_commit": "1684e0455978b46ddad607e09d85a1af5657ab1a",
        "reported_line": 105,
        "end_line": 105,
        "start_column": 18,
        "end_column": 48,
        "exact_span_sha256": "fe1f1dd755c5d96583753082c7fa4ae2be2dfd1a6bc371c240d5887bc3197945",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_seed_cli.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 72,
        "end_line": 72,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_seed_pg.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 380,
        "end_line": 380,
        "start_column": 51,
        "end_column": 72,
        "exact_span_sha256": "0b1c32a3a906b1cbb3e54b26c76eb430044e421008f76e9b6a2edea7d9836ffe",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 266,
        "end_line": 266,
        "start_column": 44,
        "end_column": 70,
        "exact_span_sha256": "dd7d51714550d1e9ae38863dfc91e83f7ecc1ff6a598762e2f06750db1b161e0",
        "match_sha256": "e7604b8b7a79c4930b78516ef572619404fa3858f7fa5099ccc7dfe4505b1f7d",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_legacy_subnet.py",
        "source_commit": "4e267522c353074d583a29c89e9022d4f8d93f33",
        "reported_line": 57,
        "end_line": 57,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/acceptance/v4-0/TTL_F1.json",
        "source_commit": "ee1dab651b1b42b99f602a02205a3d8710bb6fd9",
        "reported_line": 10,
        "end_line": 10,
        "start_column": 7,
        "end_column": 58,
        "exact_span_sha256": "db49de282d54de455455c517d10e38ace8d1de2125cffeed47b8d1b902b169f3",
        "match_sha256": "045df48130ac4b19b5488f72d64464b09bbd478264c38218d76fa5c1ef99e7c5",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/review/SCAN_f341.md",
        "source_commit": "8dedb22016bcbd8d66c20c23adc899b6b0c43559",
        "reported_line": 7,
        "end_line": 7,
        "start_column": 162,
        "end_column": 193,
        "exact_span_sha256": "53393d547dc8e044a97e4036e69d20147b037c6d0b5f3a7fcd8ceb1d086a852a",
        "match_sha256": "c19e9b295b94b965138099d32450b795e1ce73cf2542c9d3576419c5ea56f3a0",
    },
)

V4_PREFLIGHT_HISTORY: tuple[dict[str, Any], ...] = (
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "8e9d87ae500f5fab22131ab6b76d7f5bb1d505a6",
        "reported_line": 220,
        "end_line": 220,
        "start_column": 39,
        "end_column": 68,
        "exact_span_sha256": "717aecdd18fac4e6cc7b9a057f6cf59741beb662440a475f267c9cdabe243e8c",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "8e9d87ae500f5fab22131ab6b76d7f5bb1d505a6",
        "reported_line": 222,
        "end_line": 222,
        "start_column": 30,
        "end_column": 59,
        "exact_span_sha256": "04a90c4bd9c229c2d68c406fa4d367e18912ab5a1e357e9526792100866429ae",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "8e9d87ae500f5fab22131ab6b76d7f5bb1d505a6",
        "reported_line": 367,
        "end_line": 367,
        "start_column": 45,
        "end_column": 81,
        "exact_span_sha256": "b40316de11ee2760c5bca9ed70dfdf7885f89ec90d8db77d8e4d76fdc3bd3987",
        "match_sha256": "9f8edb26e9baf5474a20e14ef0c07ec90391dd1fde8c79ac7648657a16ff3b53",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "8e9d87ae500f5fab22131ab6b76d7f5bb1d505a6",
        "reported_line": 385,
        "end_line": 385,
        "start_column": 10,
        "end_column": 47,
        "exact_span_sha256": "0f62de7a54e402563bc2e792481dc68b87b6b034d6cf6d9175d5f508b4d9c967",
        "match_sha256": "044857216fb64994e9715a78b57820aafdcf054dd888c32d8e61717377cb507a",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "09f7d6ed8fabb13161c391320e8fb37fb9777033",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "65a09b1ce73ef79996144d63b3aa78bd8121d7a9",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "cb85d76c361843224c3ef9066a769c7d7f2a684e",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "9f846be67321006193c688f6209591465c2ca767",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "9f846be67321006193c688f6209591465c2ca767",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "5e61cf9b007ca21e8d4ebe04a1f7e9a210bcda02",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "5e61cf9b007ca21e8d4ebe04a1f7e9a210bcda02",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "754f22cfc66c030756c4aa6b341b5d65f85e0bcd",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "754f22cfc66c030756c4aa6b341b5d65f85e0bcd",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 118,
        "end_line": 119,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 220,
        "end_line": 220,
        "start_column": 39,
        "end_column": 68,
        "exact_span_sha256": "717aecdd18fac4e6cc7b9a057f6cf59741beb662440a475f267c9cdabe243e8c",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 222,
        "end_line": 222,
        "start_column": 30,
        "end_column": 59,
        "exact_span_sha256": "04a90c4bd9c229c2d68c406fa4d367e18912ab5a1e357e9526792100866429ae",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 351,
        "end_line": 351,
        "start_column": 11,
        "end_column": 40,
        "exact_span_sha256": "0385f1ec491185e384352946f893e8aed2373023b7ac5c2967d1da50068d1273",
        "match_sha256": "7ef80a218c721c53c39c59797ac234908fa362326c3a16bd27212f39ed9cd066",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 367,
        "end_line": 367,
        "start_column": 45,
        "end_column": 81,
        "exact_span_sha256": "b40316de11ee2760c5bca9ed70dfdf7885f89ec90d8db77d8e4d76fdc3bd3987",
        "match_sha256": "9f8edb26e9baf5474a20e14ef0c07ec90391dd1fde8c79ac7648657a16ff3b53",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 385,
        "end_line": 385,
        "start_column": 10,
        "end_column": 47,
        "exact_span_sha256": "0f62de7a54e402563bc2e792481dc68b87b6b034d6cf6d9175d5f508b4d9c967",
        "match_sha256": "044857216fb64994e9715a78b57820aafdcf054dd888c32d8e61717377cb507a",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 406,
        "end_line": 406,
        "start_column": 46,
        "end_column": 82,
        "exact_span_sha256": "f14569df8150ea3f77d091db08ed46777d518c2cb3eb7ca7ed14861bcec3a7e3",
        "match_sha256": "28c024d9aec42b9c593d110365f31b8851854b35c35374d43707f8cc6cd8cec5",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "57ee959d8526fe728cfc0be8309d9430ebfa05f5",
        "reported_line": 430,
        "end_line": 430,
        "start_column": 26,
        "end_column": 53,
        "exact_span_sha256": "0953ddca366332aa9054120e733607b99fefbbcff21e510141df6b51a46caf29",
        "match_sha256": "e1a66ed14209cdae0b093f121569e5183db9b5b3ed679fce0aa095d5b1b414a8",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 118,
        "end_line": 119,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 220,
        "end_line": 220,
        "start_column": 39,
        "end_column": 68,
        "exact_span_sha256": "717aecdd18fac4e6cc7b9a057f6cf59741beb662440a475f267c9cdabe243e8c",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 222,
        "end_line": 222,
        "start_column": 30,
        "end_column": 59,
        "exact_span_sha256": "04a90c4bd9c229c2d68c406fa4d367e18912ab5a1e357e9526792100866429ae",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 351,
        "end_line": 351,
        "start_column": 11,
        "end_column": 40,
        "exact_span_sha256": "0385f1ec491185e384352946f893e8aed2373023b7ac5c2967d1da50068d1273",
        "match_sha256": "7ef80a218c721c53c39c59797ac234908fa362326c3a16bd27212f39ed9cd066",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 367,
        "end_line": 367,
        "start_column": 45,
        "end_column": 81,
        "exact_span_sha256": "b40316de11ee2760c5bca9ed70dfdf7885f89ec90d8db77d8e4d76fdc3bd3987",
        "match_sha256": "9f8edb26e9baf5474a20e14ef0c07ec90391dd1fde8c79ac7648657a16ff3b53",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 385,
        "end_line": 385,
        "start_column": 10,
        "end_column": 47,
        "exact_span_sha256": "0f62de7a54e402563bc2e792481dc68b87b6b034d6cf6d9175d5f508b4d9c967",
        "match_sha256": "044857216fb64994e9715a78b57820aafdcf054dd888c32d8e61717377cb507a",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 406,
        "end_line": 406,
        "start_column": 46,
        "end_column": 82,
        "exact_span_sha256": "f14569df8150ea3f77d091db08ed46777d518c2cb3eb7ca7ed14861bcec3a7e3",
        "match_sha256": "28c024d9aec42b9c593d110365f31b8851854b35c35374d43707f8cc6cd8cec5",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 430,
        "end_line": 430,
        "start_column": 26,
        "end_column": 53,
        "exact_span_sha256": "0953ddca366332aa9054120e733607b99fefbbcff21e510141df6b51a46caf29",
        "match_sha256": "e1a66ed14209cdae0b093f121569e5183db9b5b3ed679fce0aa095d5b1b414a8",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_strict_response.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 12,
        "end_line": 12,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 116,
        "end_line": 117,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 292,
        "end_line": 292,
        "start_column": 11,
        "end_column": 40,
        "exact_span_sha256": "0385f1ec491185e384352946f893e8aed2373023b7ac5c2967d1da50068d1273",
        "match_sha256": "7ef80a218c721c53c39c59797ac234908fa362326c3a16bd27212f39ed9cd066",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 304,
        "end_line": 304,
        "start_column": 44,
        "end_column": 80,
        "exact_span_sha256": "dbaaedf38b425a746ef8a6ce115fc5dbfd11da130a75b7b6833b1e88a02adce1",
        "match_sha256": "9f8edb26e9baf5474a20e14ef0c07ec90391dd1fde8c79ac7648657a16ff3b53",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 322,
        "end_line": 322,
        "start_column": 46,
        "end_column": 82,
        "exact_span_sha256": "f14569df8150ea3f77d091db08ed46777d518c2cb3eb7ca7ed14861bcec3a7e3",
        "match_sha256": "28c024d9aec42b9c593d110365f31b8851854b35c35374d43707f8cc6cd8cec5",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 345,
        "end_line": 345,
        "start_column": 26,
        "end_column": 53,
        "exact_span_sha256": "0953ddca366332aa9054120e733607b99fefbbcff21e510141df6b51a46caf29",
        "match_sha256": "e1a66ed14209cdae0b093f121569e5183db9b5b3ed679fce0aa095d5b1b414a8",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "source_commit": "86ca8b8c9262f1bbce9f5b28605a754f42b07a76",
        "reported_line": 363,
        "end_line": 363,
        "start_column": 29,
        "end_column": 58,
        "exact_span_sha256": "062c0d8553421787a9115bde502aa13bd2ac00c436ea04fbc1ee50447f0ad700",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "dc1fc05befe771e63d62b575380154fb5efb635c",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "dc1fc05befe771e63d62b575380154fb5efb635c",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "c95b09f30ea0b1f81c43b78782abdd32fe66db20",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "c95b09f30ea0b1f81c43b78782abdd32fe66db20",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_supervisor.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 122,
        "end_line": 122,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "588e309c0fd6d4fcd60fa4849687abf99eab3bbd",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "588e309c0fd6d4fcd60fa4849687abf99eab3bbd",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 109,
        "end_line": 109,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 219,
        "end_line": 219,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 297,
        "end_line": 297,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "34e895eb1e873027b2201d7bd159d464200e39ae",
        "reported_line": 325,
        "end_line": 325,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "a4d8336caa160abba6efdf0cfaae1a87e71e95e5",
        "reported_line": 139,
        "end_line": 140,
        "start_column": 3,
        "end_column": 20,
        "exact_span_sha256": "d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04",
        "match_sha256": "2f0d750617ebff1ddc4bd6e66bae608c60b2f9ff2ce7d86524fcb6c402c746be",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "source_commit": "a4d8336caa160abba6efdf0cfaae1a87e71e95e5",
        "reported_line": 264,
        "end_line": 264,
        "start_column": 67,
        "end_column": 101,
        "exact_span_sha256": "94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9",
        "match_sha256": "5fafdeefa7fe7a6198bec964cd2bb4214284d7d24a6117f1ddd7584b506d4ec9",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "7dd170fd6d582d9d6d74754145a1793c9f37bb35",
        "reported_line": 71,
        "end_line": 71,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "10276796f6bda05e7e2bcdb7ba240bc70434b286e424249179685824a34a3363",
        "match_sha256": "94b393277ca683c9f02c382c5d8d91d0f2590c3d8463ea71c9932728cb3032a9",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "4556f0874abf81f613ee1b938d3d67f7b0977af9",
        "reported_line": 84,
        "end_line": 84,
        "start_column": 6,
        "end_column": 64,
        "exact_span_sha256": "a8b7d2dab131363a39ecd7bb344cb3be1b99800aff98441d94b6e669bb0ff97d",
        "match_sha256": "d71ece3ce74a7079b002e2b5941a7f883b1a1415e52237a96df11bf77ddfdd8e",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "bb4d6e48b6413f3b3735efa6f05e2090d8d4323e",
        "reported_line": 83,
        "end_line": 83,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e",
        "match_sha256": "1a6523207f88d27bc1cfa16d3b503fc70a8d08a458298f3c796b3f60afdc12cd",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/lib/v4-context.mjs",
        "source_commit": "bb4d6e48b6413f3b3735efa6f05e2090d8d4323e",
        "reported_line": 88,
        "end_line": 88,
        "start_column": 8,
        "end_column": 56,
        "exact_span_sha256": "18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e",
        "match_sha256": "1a6523207f88d27bc1cfa16d3b503fc70a8d08a458298f3c796b3f60afdc12cd",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/app/v4/[[...path]]/page.tsx",
        "source_commit": "17f96981375b56cca3172009292e89127b8d9fc3",
        "reported_line": 9,
        "end_line": 9,
        "start_column": 42,
        "end_column": 115,
        "exact_span_sha256": "87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b",
        "match_sha256": "896d3957535652b65e2eb532731f764c8b1d7f6eafe0bbc90df606658c4b367b",
    },
    {
        "rule": "generic-api-key",
        "path": "backend/src/commerceops/infrastructure/v4_demo_sessions.py",
        "source_commit": "d57808f0627821ab202e054e7d464fa2d4b9798c",
        "reported_line": 133,
        "end_line": 133,
        "start_column": 28,
        "end_column": 78,
        "exact_span_sha256": "6010903555ef6d9dd8a07f2798439009762f93c2694e7171a02fc6af17310616",
        "match_sha256": "847110db021532757d13f6e902f8a849f8ad9b4d188c633de6390f8b5e5b4fab",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/review/SCAN_a4f.md",
        "source_commit": "b726949b670153d9b5393225f890f0c919ee6ea5",
        "reported_line": 28,
        "end_line": 28,
        "start_column": 216,
        "end_column": 245,
        "exact_span_sha256": "5189f504e28b860e65ff5157f7e13fdeac74a5f2941df3ddf045bcb03e902730",
        "match_sha256": "4caa415fafdbaecfc7c282217da6c5d66ace85e42b572ec6c65fe1fe9eac5acd",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "31d11cc76c13a7a56afc5fec541b1657dc747cab",
        "reported_line": 151,
        "end_line": 151,
        "start_column": 20,
        "end_column": 50,
        "exact_span_sha256": "5ae7df16f7216f67ea2645dcef5730b23e9cf1d886985b1f58ecbd1fceb07259",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "31d11cc76c13a7a56afc5fec541b1657dc747cab",
        "reported_line": 170,
        "end_line": 170,
        "start_column": 49,
        "end_column": 70,
        "exact_span_sha256": "7293c9a4fd3f141f0a1aae4e56ff1e36c79a500a8541c0c7b65af6584d1ab0a1",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "31d11cc76c13a7a56afc5fec541b1657dc747cab",
        "reported_line": 197,
        "end_line": 197,
        "start_column": 51,
        "end_column": 72,
        "exact_span_sha256": "0b1c32a3a906b1cbb3e54b26c76eb430044e421008f76e9b6a2edea7d9836ffe",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_ttl_probe.py",
        "source_commit": "385c35599fc57a33ae2ebeeef881c6a4b8a1cbcc",
        "reported_line": 137,
        "end_line": 137,
        "start_column": 5,
        "end_column": 50,
        "exact_span_sha256": "d9750ce8385dbb070189901b02ded4ed09d2f868244afdca4c8e8ce7dabac003",
        "match_sha256": "5e4ad6f415caa2abda096640ea1af5414dd9d0e6beb00eadb1bfc8da2b4811c0",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_seed_cli.py",
        "source_commit": "2332f738885ebd0608cbe1ce670ae434116588fb",
        "reported_line": 72,
        "end_line": 72,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "frontend/v4-tests/lifecycle.waiter.mjs",
        "source_commit": "0476f8203a9fe08eedf4c48c2bf3ddbc1d01bdcd",
        "reported_line": 9,
        "end_line": 9,
        "start_column": 10,
        "end_column": 63,
        "exact_span_sha256": "c8b2b58b10acf12b247f59937a6fd4f4ee4170230d53b7dc806e0c41ce9f5cd6",
        "match_sha256": "0e979f26f5711d6c7674669d81cf34c804a8bc314f386508b229dc20989cd730",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "source_commit": "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "reported_line": 19,
        "end_line": 19,
        "start_column": 2,
        "end_column": 45,
        "exact_span_sha256": "cfdb4732beb794c9d3e5092094e8f7c7123b45e0ad9ad04dc387ee54008008c8",
        "match_sha256": "eefb48d27a20ef5ccd633e9291b72ac3e56eefbc95276bb7db73015c53a26a8c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "source_commit": "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "reported_line": 112,
        "end_line": 112,
        "start_column": 18,
        "end_column": 48,
        "exact_span_sha256": "fe1f1dd755c5d96583753082c7fa4ae2be2dfd1a6bc371c240d5887bc3197945",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "source_commit": "1c192d434caf402c3edd6cf59fe70ba183a8ca89",
        "reported_line": 262,
        "end_line": 262,
        "start_column": 44,
        "end_column": 70,
        "exact_span_sha256": "dd7d51714550d1e9ae38863dfc91e83f7ecc1ff6a598762e2f06750db1b161e0",
        "match_sha256": "e7604b8b7a79c4930b78516ef572619404fa3858f7fa5099ccc7dfe4505b1f7d",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_negatives.py",
        "source_commit": "ce51c42d629da4db339f0100ad60879fd2a465fc",
        "reported_line": 34,
        "end_line": 34,
        "start_column": 43,
        "end_column": 64,
        "exact_span_sha256": "9eae89315546427045520b575cb3ef7d7e6578ccdb9da58d34c78982841a8272",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_driver.py",
        "source_commit": "ce51c42d629da4db339f0100ad60879fd2a465fc",
        "reported_line": 484,
        "end_line": 484,
        "start_column": 10,
        "end_column": 44,
        "exact_span_sha256": "257d31b06b9ca99bcf1d666842c5dd8771b960a3aec485e029f620614fe3b267",
        "match_sha256": "f5d8f078e1d354c22377e9c092e9cdde6d794776f5a9fdcb32257cae559f277f",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/v4/test_demo_seed_pg.py",
        "source_commit": "dc439e92ea561ea7d0c95e7ef255d0fc7237f26a",
        "reported_line": 380,
        "end_line": 380,
        "start_column": 51,
        "end_column": 72,
        "exact_span_sha256": "0b1c32a3a906b1cbb3e54b26c76eb430044e421008f76e9b6a2edea7d9836ffe",
        "match_sha256": "73d3414f0d8555aae77ce476eefd9af83978c299f6afd2e446ef43e96d9279ee",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/test_legacy_subnet.py",
        "source_commit": "4e267522c353074d583a29c89e9022d4f8d93f33",
        "reported_line": 57,
        "end_line": 57,
        "start_column": 22,
        "end_column": 52,
        "exact_span_sha256": "41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada",
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/acceptance/v4-0/TTL_F1.json",
        "source_commit": "ee1dab651b1b42b99f602a02205a3d8710bb6fd9",
        "reported_line": 10,
        "end_line": 10,
        "start_column": 7,
        "end_column": 58,
        "exact_span_sha256": "db49de282d54de455455c517d10e38ace8d1de2125cffeed47b8d1b902b169f3",
        "match_sha256": "045df48130ac4b19b5488f72d64464b09bbd478264c38218d76fa5c1ef99e7c5",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/review/SCAN_f341.md",
        "source_commit": "8dedb22016bcbd8d66c20c23adc899b6b0c43559",
        "reported_line": 7,
        "end_line": 7,
        "start_column": 162,
        "end_column": 193,
        "exact_span_sha256": "53393d547dc8e044a97e4036e69d20147b037c6d0b5f3a7fcd8ceb1d086a852a",
        "match_sha256": "c19e9b295b94b965138099d32450b795e1ce73cf2542c9d3576419c5ea56f3a0",
    },
    {
        "rule": "generic-api-key",
        "path": "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        "source_commit": "42acf36571134ccb8ca277088098b05af395ba04",
        "reported_line": 4,
        "end_line": 4,
        "start_column": 5,
        "end_column": 48,
        "exact_span_sha256": "acd26a0ef07569e7f142448bb97a86f3293eff69abb69e400f70d2be55257911",
        "match_sha256": "5bbce8764fbe2008b0cbcdf1e32161ab6ee6fa458fce9738272616ddee00b2a0",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/test_v4_scan_compat.py",
        "source_commit": "44633302af915358771c32875d27a1b8ac3e7860",
        "reported_line": 1128,
        "end_line": 1128,
        "start_column": 13,
        "end_column": 53,
        "exact_span_sha256": "11ba67c032185fd580d6aac2788c22d36007598910f0ec5db9a5dbd56dcd986c",
        "match_sha256": "410e0fc24ad03d7f93c52fc3e10177fc41674bc1056307351c1f0b6cccff120c",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/test_v4_scan_compat.py",
        "source_commit": "44633302af915358771c32875d27a1b8ac3e7860",
        "reported_line": 1131,
        "end_line": 1131,
        "start_column": 15,
        "end_column": 44,
        "exact_span_sha256": "f7d28318c0db6ce5803ed3ef8d6b0710cd5fcf1879c424e53e1ac86e3c6d1b0d",
        "match_sha256": "410e0fc24ad03d7f93c52fc3e10177fc41674bc1056307351c1f0b6cccff120c",
    },
)


V4_MERGE_COPY_ANCHORS: tuple[dict[str, str], ...] = (
    {
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "path": "frontend/app/v4/[[...path]]/page.tsx",
        "blob": "60e878cab70e13abc4e827af83eebdb3ad159ad7",
    },
    {
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "path": "tests/e2e/v4/test_strict_response.py",
        "blob": "1cf5844b8b0f46fc5d0b5e298a28a031b9ca139c",
    },
    {
        "source_commit": "b726949b670153d9b5393225f890f0c919ee6ea5",
        "path": "docs/v4/review/SCAN_a4f.md",
        "blob": "2150dfeb4328fad138da3dd2636bae8cf81fbdf6",
    },
    {
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "path": "tests/e2e/v4/test_supervisor.py",
        "blob": "b7b18721733539fd615fbef891bac12dc710d27a",
    },
    {
        "source_commit": "534844a848b7e4412a6b4b2ff178f7d0aa56c82e",
        "path": "backend/src/commerceops/infrastructure/v4_demo_sessions.py",
        "blob": "bf11ab994c683019b83bcf6510daa5ffd9be62a3",
    },
    {
        "source_commit": "63a5a4f08bad6b98fe95942598291e0714bc09da",
        "path": "frontend/lib/v4-context.mjs",
        "blob": "c05c82b186f1e52f26657fd03ce817472074936c",
    },
    {
        "source_commit": "534844a848b7e4412a6b4b2ff178f7d0aa56c82e",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "blob": "44bc08da5e49b83563ed8c987ea7e6017ccef0df",
    },
    {
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "blob": "b23e358dd29b065ce2229be8a1870c702a5f6e71",
    },
    {
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "path": "tests/e2e/v4/http_probe.py",
        "blob": "d2f7dd62c119b0f1141f26e1786cfa47273a3743",
    },
    {
        "source_commit": "534844a848b7e4412a6b4b2ff178f7d0aa56c82e",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "blob": "831194f4e26a5ae554e89e1d0d297a64cc863f17",
    },
    {
        "source_commit": "534844a848b7e4412a6b4b2ff178f7d0aa56c82e",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "blob": "018748c90bc4145e3147454052296ea4a8119071",
    },
    {
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "path": "backend/migrations/versions/0024_v4_demo_foundation.py",
        "blob": "2a833ba4021fd76f3ed08b235b802701a1765d4d",
    },
    {
        "source_commit": "0476f8203a9fe08eedf4c48c2bf3ddbc1d01bdcd",
        "path": "frontend/v4-tests/lifecycle.waiter.mjs",
        "blob": "ec74f8c560ad293821dcd4545c275395c243d3d0",
    },
    {
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "path": "tests/e2e/v4/owned_negatives.py",
        "blob": "7b161c41af7bc21bd52cbe28574adfdcefc967ce",
    },
    {
        "source_commit": "2332f738885ebd0608cbe1ce670ae434116588fb",
        "path": "tests/v4/test_demo_seed_cli.py",
        "blob": "0506ca7ef27bbd4307bad5e0afb6f12a23cf3e95",
    },
    {
        "source_commit": "385c35599fc57a33ae2ebeeef881c6a4b8a1cbcc",
        "path": "tests/e2e/v4/test_ttl_probe.py",
        "blob": "fb85ea2134f1881840a1563a1b9f2bcb0090f845",
    },
    {
        "source_commit": "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "blob": "721126a713ac58eeb60a69757c32d78892839fdb",
    },
    {
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "path": "tests/v4/test_demo_seed_pg.py",
        "blob": "99883cfedb7a3e45517848b5943763c530b8ce22",
    },
    {
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "path": "tests/e2e/v4/owned_driver.py",
        "blob": "5ee68d13cd31186bdc0182aca637560343dd58a9",
    },
    {
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "path": "docs/v4/design/IDENTITY_SQL_PLAN.md",
        "blob": "dee7485487d306ab56102a76bdbaf88a83cd52c2",
    },
    {
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "blob": "97e976d67a8bf6ddcb91d8e0f77a26d60dcd4b2f",
    },
    {
        "source_commit": "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "path": "tests/e2e/v4/owned_driver.py",
        "blob": "767731bd7b730e9bab486339c77ee11b30050370",
    },
    {
        "source_commit": "dc439e92ea561ea7d0c95e7ef255d0fc7237f26a",
        "path": "tests/v4/test_demo_seed_pg.py",
        "blob": "da824e086a1f41d75e4084f7cba6daf750c882b4",
    },
    {
        "source_commit": "dc439e92ea561ea7d0c95e7ef255d0fc7237f26a",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "blob": "b7d3003f000201cbd84a22557328729991a07032",
    },
    {
        "source_commit": "823b132766184b3f35b93d0e306f4182da23ce38",
        "path": "tests/v4/test_demo_sessions_pg.py",
        "blob": "a8af7c1b587a766f84e253948c8eecac6fed4cb2",
    },
    {
        "source_commit": "1684e0455978b46ddad607e09d85a1af5657ab1a",
        "path": "tests/e2e/v4/owned_driver.py",
        "blob": "9f168bab0b31f627843d05d65e391b99bc4ca438",
    },
    {
        "source_commit": "1684e0455978b46ddad607e09d85a1af5657ab1a",
        "path": "tests/e2e/v4/test_owned_review_fixes.py",
        "blob": "0b51b2c3775c0052a9f009f857a1cf317d2aaebb",
    },
    {
        "source_commit": "4e267522c353074d583a29c89e9022d4f8d93f33",
        "path": "tests/e2e/v4/test_legacy_subnet.py",
        "blob": "ac3098476addaa63aed5311afd49ff102360c737",
    },
    {
        "source_commit": "1c1525088708e12b552973ba9d0ab1b7cd6f1ec6",
        "path": "tests/e2e/v4/http_probe.py",
        "blob": "d9579c346d2d035f7df06ccfef1eb003cc74260f",
    },
    {
        "source_commit": "ee1dab651b1b42b99f602a02205a3d8710bb6fd9",
        "path": "docs/v4/acceptance/v4-0/TTL_F1.json",
        "blob": "78de4ace420feb8034e02809aaaa5dc3e9e8fbc1",
    },
    {
        "source_commit": "8dedb22016bcbd8d66c20c23adc899b6b0c43559",
        "path": "docs/v4/review/SCAN_f341.md",
        "blob": "e5208aeac80cc7ecb73b97463a58921b93726642",
    },
    {
        "source_commit": "9727cf15aba3d2b2fa27bba6b82682c403903187",
        "path": "tests/e2e/v4/owned_negatives.py",
        "blob": "f56afab50f937a6d6da724660e08d4e8c15fa2e2",
    },
    {
        "source_commit": "42acf36571134ccb8ca277088098b05af395ba04",
        "path": "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        "blob": "c3c9cd69d382fdec2b7374e9cc50e81803a279f9",
    },
    {
        "source_commit": "667cbbc5dde82c25c50ec4fa4f60e0c6f0e366c1",
        "path": "docs/v4/acceptance/v4-0/ROOT_LEDGER.json",
        "blob": "38d2c0fef2037f40a580951716e180542e8f570a",
    },
    {
        "source_commit": "fa96764cf2b8e3ab9adbb579b764f600a7d17e60",
        "path": "docs/v4/baseline/API_EVENTS_CONTRACT.md",
        "blob": "c0375ea6f87ca3c6c77fdc1ebcb91c258916b7b0",
    },
    {
        "source_commit": "fa96764cf2b8e3ab9adbb579b764f600a7d17e60",
        "path": "docs/v4/baseline/evidence/A_EXECUTION_RECEIPT.json",
        "blob": "6f557ffb294209637a0293f5b310d3477edb6435",
    },
    {
        "source_commit": "fa96764cf2b8e3ab9adbb579b764f600a7d17e60",
        "path": "docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json",
        "blob": "992581f35dec4fa94b1dc2fdb5ac79a4211909b6",
    },
    {
        "source_commit": "fa96764cf2b8e3ab9adbb579b764f600a7d17e60",
        "path": "docs/v4/baseline/reviews/M3_API_INVENTORY.json",
        "blob": "4120a447bf26812585d40ea81fc156cfdfa7400a",
    },
    {
        "source_commit": "fa96764cf2b8e3ab9adbb579b764f600a7d17e60",
        "path": "docs/v4/baseline/v4-public-openapi.json",
        "blob": "58ad090b39b70954065b9613b53a8fe65f19e193",
    },
    {
        "source_commit": "f949781fa0b9958fedeaf3303c4cf6cefdef8322",
        "path": "frontend/app/v4/[[...path]]/page.tsx",
        "blob": "6fe538b6de6f6532a8198476a0ca8a2dd9ca05ee",
    },
)


V4_MERGE_COPY_BINDINGS: tuple[dict[str, Any], ...] = (
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_driver.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 557,
        "end_line": 557,
        "start_column": 10,
        "end_column": 44,
        "exact_span_sha256": "257d31b06b9ca99bcf1d666842c5dd8771b960a3aec485e029f620614fe3b267",
        "match_sha256": "f5d8f078e1d354c22377e9c092e9cdde6d794776f5a9fdcb32257cae559f277f",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_driver.py",
        "source_commit": "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "reported_line": 540,
        "end_line": 540,
        "start_column": 10,
        "end_column": 44,
        "exact_span_sha256": "257d31b06b9ca99bcf1d666842c5dd8771b960a3aec485e029f620614fe3b267",
        "match_sha256": "f5d8f078e1d354c22377e9c092e9cdde6d794776f5a9fdcb32257cae559f277f",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 147,
        "end_line": 147,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 259,
        "end_line": 259,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 364,
        "end_line": 364,
        "start_column": 35,
        "end_column": 56,
        "exact_span_sha256": "ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/http_probe.py",
        "source_commit": "ea48a13943d269484a4ebe59ca75803bcafe429f",
        "reported_line": 394,
        "end_line": 394,
        "start_column": 23,
        "end_column": 72,
        "exact_span_sha256": "98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0",
        "match_sha256": "8ec82ed76f6ab9e030442adcb3473af2759efba1f1e202e59731d27e5e74620d",
        "binding_kind": "copy_only",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/e2e/v4/owned_negatives.py",
        "source_commit": "2330bca2e657a236ba5355b940e2f641763d026d",
        "reported_line": 44,
        "end_line": 44,
        "start_column": 43,
        "end_column": 64,
        "exact_span_sha256": "9eae89315546427045520b575cb3ef7d7e6578ccdb9da58d34c78982841a8272",
        "match_sha256": "49c7f621d5c18ce5203358ccea3853971ec8a2cfe69661241ce5c31c5f97f32f",
        "binding_kind": "copy_only",
    },
)


def v4_preflight_history_findings() -> list[dict[str, Any]]:
    """Only the 109 exact, captured historical proposal fingerprints."""
    return [
        {
            **row,
            "fingerprint": (
                f"{row['source_commit']}:{row['path']}:{row['rule']}:{row['reported_line']}"
            ),
        }
        for row in V4_PREFLIGHT_HISTORY
    ]


def v4_preflight_public_rows(root: Path) -> tuple[tuple[dict[str, Any], str], ...]:
    result = []
    for record in V4_PREFLIGHT_SNAPSHOTS:
        source = subprocess.run(
            ["git", "show", record["source_commit"] + ":" + record["path"]],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        line, end = record["reported_line"], record["end_line"]
        value = b"\n".join(rows[line - 1 : end])
        if (
            source.returncode
            or len(rows) < end
            or hashlib.sha256(value).hexdigest() != record["exact_span_sha256"]
        ):
            raise ValueError("invalid V4 preflight source")
        result.append((record, value.decode()))
    return tuple(result)


def v4_public_rows(root: Path) -> tuple[tuple[str, str, str, str, int, int], ...]:
    """Only the thirteen captured V4 public spans from the immutable A import."""
    result = []
    for path, digest, line, end, _, _, _ in V4_PUBLIC_EXCEPTIONS:
        source = subprocess.run(
            ["git", "show", V4_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        value = b"\n".join(rows[line - 1 : end])
        if source.returncode or len(rows) < end or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError("invalid V4 public source")
        result.append((path, "^" + re.escape(path) + "$", value.decode(), digest, line, end))
    return tuple(result)


def v4_public_line_regex(row: str) -> str:
    """Exact Unicode codepoints; generated text must not introduce another finding."""
    return r"^(?:\r?\n)?" + "".join(r"\x{" + format(ord(c), "x") + "}" for c in row) + "$"


def v4_history_findings() -> list[dict[str, object]]:
    return [
        {
            "rule": "generic-api-key",
            "path": path,
            "source_commit": V4_SOURCE_COMMIT,
            "reported_line": line,
            "end_line": end,
            "start_column": col,
            "end_column": end_col,
            "exact_span_sha256": digest,
            "match_sha256": match_digest,
            "fingerprint": f"{V4_SOURCE_COMMIT}:{path}:generic-api-key:{line}",
        }
        for path, digest, line, end, match_digest, col, end_col in V4_PUBLIC_EXCEPTIONS
    ]


def m3_public_line_regex(row: str) -> str:
    """Exact ASCII bytes, hex-escaped so generated regex text is not a second public finding."""
    return (
        r"^(?:\r?\n)?" + "".join(r"\x" + format(byte, "02x") for byte in row.encode("ascii")) + "$"
    )


def m3_public_rows(root: Path) -> tuple[tuple[str, str, str, str, str, int], ...]:
    """Load pinned whole rows and the one exact two-row declaration, failing closed."""
    result = []
    for commit, path, pattern, digest, line in (
        *M3_PUBLIC_EXCEPTIONS,
        *M3_HISTORY_PUBLIC_EXCEPTIONS,
    ):
        source = subprocess.run(
            ["git", "show", commit + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid M3 public source")
        result.append((commit, path, pattern, rows[line - 1].decode(), digest, line))
    for commit, path, pattern, digest, line, end in M3_SPAN_PUBLIC_EXCEPTIONS:
        source = subprocess.run(
            ["git", "show", commit + ":" + path], cwd=root, capture_output=True, check=False
        )
        rows = source.stdout.splitlines()
        value = b"\n".join(rows[line - 1 : end])
        if source.returncode or len(rows) < end or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError("invalid M3 public source")
        result.append((commit, path, pattern, value.decode(), digest, line))
    return tuple(result)


def m2_consumer_rows(root: Path) -> tuple[tuple[str, str, str, str, int], ...]:
    """Only the eight unchanged reviewed public literals at the pinned consumer revision."""
    result = []
    for path, pattern, digest, line in M2_CONSUMER_EXCEPTIONS:
        source = subprocess.run(
            ["git", "show", M2_CONSUMER_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid M2 consumer public source")
        result.append((path, pattern, rows[line - 1].decode(), digest, line))
    return tuple(result)


def m2_public_rows(root: Path) -> tuple[tuple[str, str, str, str, int], ...]:
    """Read only the two independently reviewed immutable public source lines."""
    result = []
    for path, pattern, digest, line in M2_PUBLIC_EXCEPTIONS:
        source = subprocess.run(
            ["git", "show", M2_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid M2 public source")
        result.append((path, pattern, rows[line - 1].decode(), digest, line))
    return tuple(result)


def validate_woo_public_sources(root: Path) -> None:
    """仅核Root已转交B提交的两条公开行，不读取其他WIP或运行数据。"""
    for path, _, row, digest, line in WOO_PUBLIC_EXCEPTIONS:
        if hashlib.sha256(row.encode()).hexdigest() != digest:
            raise ValueError("invalid Woo public source")
        source = subprocess.run(
            ["git", "show", WOO_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid Woo public source")


def main() -> None:
    # CI在安装依赖前运行敏感扫描；导入公开行常量不能要求生成器的开发依赖。
    import tomli_w

    from scripts.scan_secrets import APPROVED_TEST_HISTORY

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256:
        raise SystemExit("官方固定配置 SHA256 不匹配")
    config = tomllib.loads(source.decode())
    global_removed = int("allowlist" in config) + len(config.get("allowlists", []))
    config.pop("allowlist", None)
    config.pop("allowlists", None)
    rule_removed = 0
    for rule in config["rules"]:
        rule_removed += int("allowlist" in rule) + len(rule.get("allowlists", []))
        rule.pop("allowlist", None)
        rule.pop("allowlists", None)
    # 公开格式误报：只允许指定规则/文件的精确整行，不能排除文件。
    schema_row = next(
        line
        for line in (ROOT / "docs/DATA_MODEL.md").read_text().splitlines()
        if line.startswith("| identities |")
    )
    if hashlib.sha256(schema_row.encode()).hexdigest() != (
        "3716668c9be9e82d8924d3b13323c5296acb4a80402598a6e4c157dee7628838"
    ):
        raise SystemExit("公开 schema 行变化，须重新审查精确豁免")
    exceptions = []
    validate_woo_public_sources(ROOT)
    if hashlib.sha256(P3_PUBLIC_ROW.encode()).hexdigest() != P3_ROW_DIGEST:
        raise SystemExit("P3历史公开摘要行变化，须重新审查精确豁免")
    if hashlib.sha256(B_PUBLIC_ROW.encode()).hexdigest() != B_ROW_DIGEST:
        raise SystemExit("B历史公开metadata行变化，须重新审查精确豁免")
    if hashlib.sha256(RO_PUBLIC_ROW.encode()).hexdigest() != RO_ROW_DIGEST:
        raise SystemExit("RO历史公开action行变化，须重新审查精确豁免")
    for rule in config["rules"]:
        if rule["id"] == "generic-api-key":
            path = r"(?:^|/)docs/DATA_MODEL\.md$"
            row = schema_row
            reason = "公开 identities 字段说明的精确 Markdown 行"
        elif rule["id"] == "aws-amazon-bedrock-api-key-short-lived":
            path = r"(?:^|/)\.gitleaks\.toml$"
            row = "regex = " + json.dumps(rule["regex"])
            reason = "该规则自身固定 regex 声明的精确 TOML 行"
        else:
            continue
        rule["allowlists"] = [
            {
                "description": reason,
                "condition": "AND",
                "regexTarget": "line",
                "paths": [path],
                "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
            }
        ]
        exceptions.append(
            {
                "rule": rule["id"],
                "path": path,
                "reason": reason,
                "exact_line_sha256": hashlib.sha256(row.encode()).hexdigest(),
            }
        )
        if rule["id"] == "generic-api-key":
            reason = "2a194a8历史公开OpenAPI文件SHA256，Root与独审核实非凭据，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [P3_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(P3_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": P3_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": P3_ROW_DIGEST,
                    "source_commit": "2a194a8bb3b324982b1ba7a7971eb6e852ce06a6",
                    "source_line": 7,
                }
            )
            reason = "973bf64历史公开B只读验证metadata扫描状态，Root核实非凭据，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [B_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(B_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": B_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": B_ROW_DIGEST,
                    "source_commit": "973bf6447211f084355d61b9d58adfd95dfa2788",
                    "source_line": 27,
                }
            )
            reason = "348a9f4历史只读SQL audit action公开名称，Root核实整行无私有值，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [RO_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(RO_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": RO_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": RO_ROW_DIGEST,
                    "source_commit": RO_SOURCE_COMMIT,
                    "source_line": 3936,
                }
            )
            for source_path, path, row, digest, line in WOO_PUBLIC_EXCEPTIONS:
                reason = "bbb507b已核Woo公开合成marker，仅指定path及完整行，当前/index另核源行hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": WOO_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                    }
                )
            for source_path, path, row, digest, line in m2_public_rows(ROOT):
                reason = "85f477c双审公开合同名/字段名，仅指定path与完整行及固定来源hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": M2_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                    }
                )
            for source_path, path, row, digest, line in m2_consumer_rows(ROOT):
                reason = "原d42已审八行公开字段名，27af9c来源重绑定候选，仅指定path与完整行hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": M2_CONSUMER_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                    }
                )
            for commit, source_path, path, row, digest, line in m3_public_rows(ROOT):
                reason = "M3公开字段/列引用/操作名候选，仅指定path与完整行及固定来源hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [m3_public_line_regex(row)],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": commit,
                        "source_path": source_path,
                        "source_line": line,
                        **({"source_end_line": line + row.count("\n")} if "\n" in row else {}),
                    }
                )
            for source_path, path, row, digest, line, end in v4_public_rows(ROOT):
                reason = "V4公开合同/字段/摘要；仅固定来源path与完整行/span"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [v4_public_line_regex(row)],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": V4_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                        "source_end_line": end,
                    }
                )
            for record, row in v4_preflight_public_rows(ROOT):
                reason = "V4预检候选；仅固定来源path与完整行/span"
                path = "^" + re.escape(record["path"]) + "$"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [v4_public_line_regex(row)],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": record["exact_span_sha256"],
                        "source_commit": record["source_commit"],
                        "source_path": record["path"],
                        "source_line": record["reported_line"],
                        "source_end_line": record["end_line"],
                        "start_column": record["start_column"],
                        "end_column": record["end_column"],
                        "match_sha256": record["match_sha256"],
                    }
                )
    content = (
        "# Gitleaks v8.30.1 MIT 规则的固定副本；来源/生成信息见 scripts/gitleaks_rules.json。\n"
        "# 删除全部上游 allowlist；保留所有规则及正向 path/regex/entropy。\n"
        "# 不使用 extend/useDefault；仅有 96 个指定规则/路径/精确整行 AND 豁免。\n"
        + tomli_w.dumps(config)
    ).encode()
    if tomllib.loads(content.decode()) != config:
        raise SystemExit("规则 TOML 序列化语义变化，拒绝生成")
    (ROOT / ".gitleaks.toml").write_bytes(content)
    provenance = {
        "version": "8.30.1",
        "source": "https://raw.githubusercontent.com/gitleaks/gitleaks/v8.30.1/config/gitleaks.toml",
        "source_sha256": UPSTREAM_SHA256,
        "config_sha256": hashlib.sha256(content).hexdigest(),
        "rule_count": len(config["rules"]),
        "rule_ids_sha256": hashlib.sha256(
            "\n".join(sorted(rule["id"] for rule in config["rules"])).encode()
        ).hexdigest(),
        "removed_global_allowlists": global_removed,
        "removed_rule_allowlists": rule_removed,
        "exceptions": exceptions,
        "historical_findings": list(APPROVED_TEST_HISTORY),
        "v4_historical_findings": v4_history_findings(),
        "v4_additional_historical_findings": v4_additional_history_findings(),
        "v4_preflight_historical_findings": v4_preflight_history_findings(),
        "v4_merge_copy_anchors": list(V4_MERGE_COPY_ANCHORS),
        "v4_merge_copy_bindings": list(V4_MERGE_COPY_BINDINGS),
    }
    (ROOT / "scripts/gitleaks_rules.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        f"固定规则生成完成：{len(config['rules'])} rules, {len(exceptions)} exact-line exceptions"
    )


if __name__ == "__main__":
    main()
