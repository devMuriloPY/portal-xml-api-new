def limpar_cnpj(cnpj: str) -> str:
    """Remove formatação do CNPJ, deixando apenas números"""
    if not cnpj:
        return ""
    return "".join(filter(str.isdigit, cnpj))


def formatar_cnpj(cnpj: str) -> str:
    """Formata um CNPJ para o padrão XX.XXX.XXX/XXXX-XX"""
    cnpj_limpo = limpar_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return cnpj  # Retorna o original se não for um CNPJ válido de 14 dígitos

    return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
