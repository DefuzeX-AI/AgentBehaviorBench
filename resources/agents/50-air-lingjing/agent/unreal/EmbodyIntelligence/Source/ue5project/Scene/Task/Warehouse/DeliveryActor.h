#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "DeliveryActor.generated.h"

UCLASS()
class UE5PROJECT_API ADeliveryActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	ADeliveryActor();

	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UStaticMeshComponent* MarkerMesh;
	
};
