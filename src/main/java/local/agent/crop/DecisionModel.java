package local.agent.crop;

import static local.agent.crop.Contracts.*;

@FunctionalInterface
public interface DecisionModel {
    ModelDecision decide(Perception.Context context) throws Exception;
}
