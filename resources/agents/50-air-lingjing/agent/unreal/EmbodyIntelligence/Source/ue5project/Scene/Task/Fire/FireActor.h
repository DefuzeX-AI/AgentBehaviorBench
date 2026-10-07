#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "FireActor.generated.h"

UCLASS()
class UE5PROJECT_API AFireActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	AFireActor();

	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;
	void SetFireScale(const FVector& InScale) const;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UParticleSystemComponent* FireParticle;
};
