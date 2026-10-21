package local.agent;

import com.sun.net.httpserver.HttpServer;
import local.agent.crop.Contracts.SearchQuery;
import local.agent.crop.HttpKnowledgeSearch;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class HttpKnowledgeSearchTest {
    @Test void postsQueryWithAuthenticationAndParsesEvidence() throws Exception {
        var receivedBody = new AtomicReference<String>();
        var receivedAuth = new AtomicReference<String>();
        var receivedMethod = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/search", exchange -> {
            receivedMethod.set(exchange.getRequestMethod());
            receivedAuth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            receivedBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = """
                {"matches":[{"id":"test-n","nutrient":"氮","crops":["水稻"],
                "text":"测试证据","sourceUrl":"https://example.org/fixture","score":0.8}]}
                """.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            var client = new HttpKnowledgeSearch(
                    URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/search"), "test-token");
            var matches = client.search(new SearchQuery("水稻", "老叶发黄", 8));
            assertEquals("POST", receivedMethod.get());
            assertEquals("Bearer test-token", receivedAuth.get());
            assertTrue(receivedBody.get().contains("老叶发黄"));
            assertEquals("氮", matches.get(0).nutrient());
        } finally {
            server.stop(0);
        }
    }

    @Test void rejectsNonSuccessResponsesInsteadOfTreatingThemAsEmptyKnowledge() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/search", exchange -> {
            exchange.sendResponseHeaders(503, -1);
            exchange.close();
        });
        server.start();
        try {
            var client = new HttpKnowledgeSearch(
                    URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/search"), null);
            assertThrows(IllegalStateException.class,
                    () -> client.search(new SearchQuery("水稻", "老叶发黄", 8)));
        } finally {
            server.stop(0);
        }
    }
}
