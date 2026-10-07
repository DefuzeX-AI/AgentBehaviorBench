#pragma once

#include "CoreMinimal.h"
#include "CameraActorBase.h"
#include "SceneCameraActor.generated.h"

class UCesiumGlobeAnchorComponent;


UCLASS()
class UE5PROJECT_API ASceneCameraActor : public ACameraActorBase
{
	GENERATED_BODY()

public:
	ASceneCameraActor();

protected:
	virtual void OnScrollUp() override;
	virtual void OnScrollDown() override;


	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Cesium")
	UCesiumGlobeAnchorComponent* GlobeAnchor;
};
