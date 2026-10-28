"""
Analisis bertanda (polaritas relasional) sengaja tidak diterbitkan.

Tanda tepi hanya bisa dihitung sebagai aritmetika dua atribut simpul:
sentimen A dikurangi sentimen B. Pada graf yang komunitasnya homogen, hasilnya
selalu terbaca "seimbang", dan pada graf yang heterogen ia mengukur selisih
rata-rata, bukan hubungan. Angka seperti itu akan dibaca sebagai temuan
tentang hubungan antar-entitas padahal hanya cermin dua angka yang sudah ada.

Karena itu keluarannya hanya status dan alasan. Tidak ada kunci angka di sini,
dan menambahkannya berarti membatalkan keputusan D6 di rencana SNA 10/10 —
bukan sekadar menambah satu field.
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.build import NetworkBundle

NOT_PUBLISHED = "not_published"
REASON = (
    "Polaritas relasional tidak dihitung: tanda tepi hanya bisa diturunkan "
    "dari selisih dua skor simpul, sehingga ia mengukur selisih rata-rata, "
    "bukan hubungan. Sentimen tetap tersedia per entitas."
)


def signed_edges(network: NetworkBundle) -> Dict[str, Any]:
    """
    Status analisis bertanda; selalu `not_published`, dengan alasan tertulis.

    `network` diterima supaya bentuk keluarannya bisa menyebut apakah lapisan
    sentimen ada — tanpa itu, pembaca tidak tahu apakah penolakan ini berlaku
    untuk korpus yang memang punya data sentimen.
    """
    has_sentiment = network.sentiment is not None
    return {
        "status": NOT_PUBLISHED,
        "reason": REASON,
        "entity_sentiment": "ready" if has_sentiment else "awaiting_input",
    }