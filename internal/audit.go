// Agent OS - Audit Logging
// Co-Founder & Author: Emodv

package internal

import (
	"log"
	"time"
)

func Audit(agentID, action, metadata string) {
	log.Printf("[AUDIT] time=%s agent=%s action=%s meta=%s",
		time.Now().Format(time.RFC3339),
		agentID,
		action,
		metadata,
	)
}
