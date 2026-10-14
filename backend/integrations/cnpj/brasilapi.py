"""Consulta real à BrasilAPI (https://brasilapi.com.br). Nunca usada nos testes."""

import json
import urllib.error
import urllib.request

from integrations.cnpj.base import CnpjData, CnpjLookup, CnpjLookupError, CnpjNotFound

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


class BrasilApiCnpjLookup(CnpjLookup):
    def lookup(self, cnpj, *, timeout):
        request = urllib.request.Request(
            URL.format(cnpj=cnpj), headers={"Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (400, 404):
                raise CnpjNotFound("CNPJ não encontrado na BrasilAPI.") from error
            raise CnpjLookupError(f"BrasilAPI respondeu {error.code}.") from error
        except (OSError, ValueError) as error:  # URLError, timeout e JSON inválido
            raise CnpjLookupError("BrasilAPI indisponível.") from error
        return self._parse(cnpj, payload)

    @staticmethod
    def _parse(cnpj, payload):
        if not isinstance(payload, dict) or not payload.get("razao_social"):
            raise CnpjLookupError("Resposta inesperada da BrasilAPI.")
        street_parts = (payload.get("descricao_tipo_de_logradouro"), payload.get("logradouro"))
        street = " ".join(part for part in street_parts if part)
        return CnpjData(
            cnpj=cnpj,
            legal_name=payload["razao_social"],
            trade_name=payload.get("nome_fantasia") or "",
            registration_status=payload.get("descricao_situacao_cadastral") or "",
            street=street,
            number=payload.get("numero") or "",
            complement=payload.get("complemento") or "",
            district=payload.get("bairro") or "",
            city=payload.get("municipio") or "",
            state=payload.get("uf") or "",
            zip_code="".join(c for c in str(payload.get("cep") or "") if c.isdigit()),
        )
