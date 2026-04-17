from state import GraphState

def retrieval_agent(state: GraphState) -> GraphState:
    """
    Agent ten normalnie wykonywałby wyszukiwanie w bazie wektorowej pobierając 
    odpowiednie kawałki (chunks) na podstawie pytania.
    Tu upraszczamy - podajemy cały XML jako kontekst tekstowy RAG.
    """
    # W docelowym RAG tu wybralibyśmy tylko pasujący fragment.
    return {}
