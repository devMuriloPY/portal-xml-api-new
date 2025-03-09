def formatar_cnpj(cnpj: str) -> str:
    """Formata um CNPJ para o padrão XX.XXX.XXX/XXXX-XX"""
    if len(cnpj) != 14 or not cnpj.isdigit():
        return cnpj  # Retorna o original se não for um CNPJ válido de 14 dígitos

    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
