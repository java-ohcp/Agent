package local.agent.crop;

import java.util.List;
import static local.agent.crop.Contracts.*;

@FunctionalInterface
public interface KnowledgeSearch {
    List<Evidence> search(SearchQuery query) throws Exception;
}
