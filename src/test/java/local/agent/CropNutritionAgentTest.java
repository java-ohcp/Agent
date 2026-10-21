package local.agent;

import local.agent.crop.*;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import static local.agent.crop.Contracts.*;
import static org.junit.jupiter.api.Assertions.*;

class CropNutritionAgentTest {
    private final Input input = new Input("水稻", "老叶均匀黄化，分蘖减少", "分蘖期", "", "", "");
    // Synthetic fixtures, not a production knowledge base.
    private final Evidence evidence = new Evidence("fixture-n", "氮", List.of("水稻"),
            "测试症状证据", "https://example.org/test-fixture", 0.85);

    @Test void returnsCandidatesGroundedInBackendEvidence() {
        var agent = new CropNutritionAgent(q -> List.of(evidence),
                c -> new ModelDecision("READY", List.of("fixture-n"), List.of()), 0.5);
        var result = agent.analyze(input);
        assertEquals(Status.READY, result.status());
        assertEquals("氮", result.candidates().get(0).nutrient());
        assertEquals(0.85, result.candidates().get(0).matchScore());
        assertEquals(List.of(evidence), result.evidence());
    }

    @Test void neverCallsModelWhenKnowledgeIsMissing() {
        var calls = new AtomicInteger();
        var agent = new CropNutritionAgent(q -> List.of(), c -> {
            calls.incrementAndGet();
            throw new AssertionError("No evidence must mean no model call");
        }, 0.5);
        assertEquals(Status.NEED_MORE_INFO, agent.analyze(input).status());
        assertEquals(0, calls.get());
    }

    @Test void rejectsInventedEvidenceWithBoundedRetry() {
        var calls = new AtomicInteger();
        var agent = new CropNutritionAgent(q -> List.of(evidence), c -> {
            calls.incrementAndGet();
            return new ModelDecision("READY", List.of("invented"), List.of());
        }, 0.5);
        var result = agent.analyze(input);
        assertEquals(Status.NEED_MORE_INFO, result.status());
        assertTrue(result.candidates().isEmpty());
        assertEquals(2, calls.get());
    }

    @Test void filtersWrongCropAndLowScoresBeforeModelCall() {
        var wrong = new Evidence("wrong", "钾", List.of("番茄"), "测试证据", "test", 0.99);
        var weak = new Evidence("weak", "磷", List.of("水稻"), "测试证据", "test", 0.1);
        var agent = new CropNutritionAgent(q -> List.of(evidence, wrong, weak), c -> {
            assertEquals(List.of(evidence), c.evidence());
            return new ModelDecision("READY", List.of(evidence.id()), List.of());
        }, 0.5);
        assertEquals(Status.READY, agent.analyze(input).status());
    }

    @Test void reportsKnowledgeOutageWithoutFabricatingDiagnosis() {
        var agent = new CropNutritionAgent(q -> { throw new java.io.IOException("offline"); },
                c -> { throw new AssertionError("Must not call model"); }, 0.5);
        assertEquals(Status.KNOWLEDGE_UNAVAILABLE, agent.analyze(input).status());
    }

    @Test void asksForCropRatherThanMakingAnUnscopedDiagnosis() {
        var agent = new CropNutritionAgent(q -> List.of(evidence),
                c -> { throw new AssertionError("Must not call model"); }, 0.5);
        assertEquals(Status.NEED_MORE_INFO,
                agent.analyze(new Input("", "叶片黄化", "", "", "", "")).status());
    }

    @Test void rejectsEmptySymptomsAndNormalizesExternalText() throws Exception {
        var perception = new Perception(q -> List.of());
        assertThrows(IllegalArgumentException.class,
                () -> perception.receive(new Input("水稻", "", "", "", "", "")));
        var context = perception.receive(new Input(" 水稻 ", "老叶\u0000黄化", null, null, null, null));
        assertEquals("水稻", context.input().crop());
        assertEquals("老叶 黄化", context.input().symptoms());
    }

    @Test void runsLangchain4jPlannerThroughSpringAiAndParsesJson() {
        org.springframework.ai.chat.model.ChatModel model = prompt -> {
            assertTrue(prompt.getContents().contains("evidence"));
            return new org.springframework.ai.chat.model.ChatResponse(List.of(
                    new org.springframework.ai.chat.model.Generation(
                            new org.springframework.ai.chat.messages.AssistantMessage(
                                    "{\"status\":\"READY\",\"evidenceIds\":[\"fixture-n\"],\"questions\":[]}"))));
        };
        var planner = new SpringAiDecisionModel(model);
        var agent = new CropNutritionAgent(q -> List.of(evidence), planner, 0.5);
        assertEquals(Status.READY, agent.analyze(input).status());
    }
}
